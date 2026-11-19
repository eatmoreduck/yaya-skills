// ncm_upload.mjs —— 批量上传目录内 MP3 到网易云音乐云盘，并加入指定歌单
// 用法: node scripts/ncm_upload.mjs --dir <MP3目录> --playlist <歌单ID> [--cookie cookie文件] [--album 专辑] [--artist 歌手]
// 前置: 先用 ego-browser 导出登录 cookie（见 SKILL.md「发布分发」一节）
// 踩坑记录见 SKILL.md，改动前必读。
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";

function arg(name, dflt) {
  const i = process.argv.indexOf("--" + name);
  return i > -1 ? process.argv[i + 1] : dflt;
}
const DIR = arg("dir");
const PLAYLIST = arg("playlist");
const COOKIE_FILE = arg("cookie", "/tmp/ncm/cookie.txt");
const ALBUM = arg("album", "yaya-corpus");
const ARTIST = arg("artist", "yaya-corpus");
if (!DIR || !PLAYLIST) {
  console.error("用法: node ncm_upload.mjs --dir <MP3目录> --playlist <歌单ID> [--cookie cookie.txt] [--album A] [--artist AR]");
  process.exit(1);
}

const cookieStr = fs.readFileSync(COOKIE_FILE, "utf8").trim();
const csrf = (cookieStr.match(/__csrf=([^;]+)/) || [])[1] || "";

// ---------- weapi 加密（网易云私有协议） ----------
const IV = Buffer.from("0102030405060708");
const PRESET = Buffer.from("0CoJUm6Qyw8W8jud");
const BASE62 = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
const PUB = crypto.createPublicKey(`-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDgtQn2JZ34ZC28NWYpAUd98iZ37BUrX/aKzmFbt7clFSs6sXqHauqKWqdtLkF2KexO40H1YTX8z2lSgBBOAxLsvaklV8k4cBFK9snQXE9/DDaFt6Rr7iVZMldczhC0JNgTz+SHXT6CBHuX3e9SdB1Ua44oncaTWz7OBGLbCiK45wIDAQAB
-----END PUBLIC KEY-----`);
const jwk = PUB.export({ format: "jwk" });
const N = BigInt("0x" + Buffer.from(jwk.n, "base64url").toString("hex"));
const E = BigInt("0x" + Buffer.from(jwk.e, "base64url").toString("hex"));

function aesCbcB64(text, key) {
  const c = crypto.createCipheriv("aes-128-cbc", key, IV);
  return Buffer.concat([c.update(Buffer.from(text, "utf8")), c.final()]).toString("base64");
}
function rsaNoPad(bytes) { // RSA no-padding: m^65537 mod n
  let m = BigInt("0x" + Buffer.from(bytes).toString("hex"));
  let r = 1n, b = m, e = E;
  while (e > 0n) { if (e & 1n) r = (r * b) % N; b = (b * b) % N; e >>= 1n; }
  return r.toString(16).padStart(256, "0");
}
function weapiEnc(obj) {
  const text = JSON.stringify(obj);
  let secret = "";
  for (let i = 0; i < 16; i++) secret += BASE62[crypto.randomInt(62)];
  return {
    params: aesCbcB64(aesCbcB64(text, PRESET), Buffer.from(secret)),
    encSecKey: rsaNoPad(secret.split("").reverse().join("")),
  };
}
async function weapi(p, data) {
  const { params, encSecKey } = weapiEnc({ ...data, csrf_token: csrf });
  const r = await fetch("https://music.163.com" + p, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      Cookie: cookieStr,
      Referer: "https://music.163.com",
      "User-Agent": "Mozilla/5.0",
    },
    body: new URLSearchParams({ params, encSecKey }).toString(),
  });
  return r.json();
}
async function weapiRetry(p, data, tries = 4) {
  let last;
  for (let i = 0; i < tries; i++) {
    try { return await weapi(p, data); }
    catch (e) { last = e; await new Promise(res => setTimeout(res, 1500 * (i + 1))); }
  }
  throw new Error("network: " + (last && last.message));
}

// 验证登录
const who = await weapiRetry("/weapi/w/nuser/account/get", {});
if (!who || !who.profile) { console.error("❌ 未登录或 cookie 失效，请重新导出 cookie"); process.exit(1); }
console.log("登录用户:", who.profile.nickname);

const BUCKET = "jd-musicrep-privatecloud-audio-public";
const NOS_UP = "http://nosup-jd1.127.net"; // lbs(wanproxy.127.net) 在代理/fake-IP 环境不可达，此节点由 lbs 下发，一般不变
const files = fs.readdirSync(DIR).filter(f => f.endsWith(".mp3")).sort();
const results = [];

for (const fname of files) {
  try {
    const buf = fs.readFileSync(path.join(DIR, fname));
    const md5hex = crypto.createHash("md5").update(buf).digest("hex");
    const song = fname.replace(/\.mp3$/, "");

    const chk = await weapiRetry("/weapi/cloud/upload/check", {
      bitrate: "999000", ext: "", length: buf.length, md5: md5hex, songId: "0", version: 1,
    });
    if (!chk || chk.code !== 200) throw new Error("check: " + JSON.stringify(chk).slice(0, 150));
    const chkSongId = chk.songId || 0;

    const tk = await weapiRetry("/weapi/nos/token/alloc", {
      bucket: "", ext: "mp3", filename: song.replace(/\s/g, "").replace(/\./g, "_"),
      local: false, nos_product: 3, type: "audio", md5: md5hex,
    });
    if (!tk || tk.code !== 200) throw new Error("alloc: " + JSON.stringify(tk).slice(0, 150));
    const { objectKey, token, resourceId } = tk.result;

    // NOS 直传：${UP}/${bucket}/${objectKey}?offset=0&complete=true&version=1.0（objectKey 不转义）
    const up = await fetch(`${NOS_UP}/${BUCKET}/${objectKey}?offset=0&complete=true&version=1.0`, {
      method: "POST",
      headers: {
        "x-nos-token": token,
        "Content-MD5": md5hex.toUpperCase(),
        "Content-Type": "audio/mpeg",
        "Content-Length": String(buf.length),
      },
      body: buf,
    });
    if (!up.ok) throw new Error("NOS: " + up.status + " " + (await up.text()).slice(0, 120));

    // 注册元数据（标题/歌手/专辑在此写入云盘条目）
    const info = await weapiRetry("/weapi/upload/cloud/info/v2", {
      md5: md5hex, songid: String(chkSongId), filename: fname,
      song: song, album: ALBUM, artist: ARTIST, bitrate: "999000", resourceId,
    });
    if (!info || info.code !== 200) throw new Error("info: " + JSON.stringify(info).slice(0, 150));

    const pub = await weapiRetry("/weapi/cloud/pub/v2", { songid: String(info.songId) });
    // 首次发布返回 {code:200}；同 MD5 重复上传返回 {privateCloud:{...}} 且无 code —— 两者都算成功
    const published = pub && (pub.code === 200 || pub.privateCloud);
    if (!published) throw new Error("pub: " + JSON.stringify(pub).slice(0, 150));
    const finalSongId = (pub.privateCloud && pub.privateCloud.songId) || info.songId;

    results.push({ fname, songId: String(finalSongId) });
    console.log(`OK ${fname} -> songId ${info.songId}`);
    await new Promise(res => setTimeout(res, 1200));
  } catch (e) {
    results.push({ fname, error: String(e.message || e) });
    console.log(`FAIL ${fname}: ${String(e.message || e).slice(0, 200)}`);
  }
}

// 加入歌单：trackIds 必须是「纯字符串数组」+ imme:'true'（[{id:...}] 会报「传入的歌曲ID错误」）
const okIds = results.filter(r => r.songId).map(r => r.songId);
console.log(`上传成功 ${okIds.length}/${files.length}`);
if (okIds.length) {
  const add = await weapiRetry("/weapi/playlist/manipulate/tracks", {
    op: "add", pid: PLAYLIST, trackIds: JSON.stringify(okIds), imme: "true",
  });
  console.log("加入歌单 =>", add.code === 200 ? "OK" : add.code === 502 ? "已在歌单（重复添加被忽略）" : JSON.stringify(add).slice(0, 200));
  if (add.code === 512) {
    const r2 = await weapiRetry("/weapi/playlist/manipulate/tracks", {
      op: "add", pid: PLAYLIST, trackIds: JSON.stringify([...okIds, ...okIds]), imme: "true",
    });
    console.log("512 重试 =>", r2.code === 200 ? "OK" : JSON.stringify(r2).slice(0, 200));
  }
}
fs.writeFileSync(path.join(DIR, "_upload_result.json"), JSON.stringify(results, null, 1));
console.log("done");
