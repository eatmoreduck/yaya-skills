// ncm_cookie_export.mjs —— 从 ego-browser 浏览器导出网易云登录 cookie
// 用法: ego-browser nodejs < scripts/ncm_cookie_export.mjs
// 前提: 浏览器里已登录 music.163.com（扫码登录，见 SKILL.md）
import fs from "node:fs";

const OUT = process.env.NCM_COOKIE_OUT || "/tmp/ncm/cookie.txt";
const task = await taskSpace("网易云 cookie 导出");
let page = (await task.pages())[0];
if (!page) {
  page = await task.newPage();
}
if (!(await page.url()).includes("music.163.com")) {
  await page.goto("https://music.163.com/", { timeout: 30000 });
  await page.waitForTimeout(3000);
}
const { cookies } = await page.cdp("Network.getCookies", { urls: ["https://music.163.com"] });
const str = cookies.map(c => `${c.name}=${c.value}`).join("; ");
fs.mkdirSync(OUT.slice(0, OUT.lastIndexOf("/")), { recursive: true });
fs.writeFileSync(OUT, str);
const hasLogin = cookies.some(c => c.name === "MUSIC_U");
console.log(`cookie 已导出到 ${OUT}（${cookies.length} 条，${hasLogin ? "已登录" : "❌ 未登录，请先在浏览器扫码登录 music.163.com"}）`);
