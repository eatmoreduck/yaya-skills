# yaya-diarize —— 说话人分离（谁在何时说话）

**音频进 → 说话人时间线出。** 只认声音、不认文字。纯本地，免费、零登录。

```bash
bash skills/yaya-diarize/run.sh recording.m4a --speakers 2
# → recording.turns.json: {"num_speakers": 2, "turns": [{start, end, speaker}, ...]}
```

- 引擎：sherpa-onnx（pyannote 分割 + CAM++ 中文声纹）。依赖和模型共享 `yaya-asr` 的环境——**首次使用先跑一次 [yaya-asr](../yaya-asr/)**。
- `--speakers N` 的**真实语义是"强制聚成 N 类"，不是上限**：人少的录音务必填真实人数；`-1` 按阈值自动聚类（长音频易过分割）。
- 编号按声纹聚类顺序，非真实姓名；不标注重叠语音。
- 缓存（源指纹+参数绑定）意味着：换音频或换参数自动重算，同参数重跑秒回。
- 在流水线里，[yaya-asr](../yaya-asr/) 会以后台进程调用本 skill，与 MLX 转写**并行执行**（GPU 转写 ∥ CPU 分离，实测零拖慢）。
