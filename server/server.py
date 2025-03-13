import asyncio
import websockets
import os
from pydub import AudioSegment
import opuslib_next
import numpy as np

async def send_opus_data(websocket):
    # 读取并编码WAV文件为Opus数据
    opus_datas, duration = wav_to_opus_data('tts-2025-03-06@48df4dcce3714e469776a19d86e3cd51.mp3')
    
    # 逐帧发送Opus数据
    for opus_data in opus_datas:
        print(f"Sending {len(opus_datas)} bytes")
        await websocket.send(opus_data)
        await asyncio.sleep(0.06)  # 控制发送速率，60ms per frame
    await websocket.send(b'END_OF_STREAM')  # 发送结束标志

def wav_to_opus_data(wav_file_path):
    # 使用pydub加载PCM文件
    file_type = os.path.splitext(wav_file_path)[1].lstrip('.')
    audio = AudioSegment.from_file(wav_file_path, format=file_type)
    duration = len(audio) / 1000.0

    # 转换为单声道和16kHz采样率（确保与编码器匹配）
    audio = audio.set_channels(1).set_frame_rate(16000)

    # 获取原始PCM数据（16位小端）
    raw_data = audio.raw_data

    # 初始化Opus编码器
    encoder = opuslib_next.Encoder(16000, 1, opuslib_next.APPLICATION_AUDIO)

    # 编码参数
    frame_duration = 60  # 60ms per frame
    frame_size = int(16000 * frame_duration / 1000)  # 960 samples/frame

    opus_datas = []
    # 按帧处理所有音频数据（包括最后一帧可能补零）
    for i in range(0, len(raw_data), frame_size * 2):  # 16bit=2bytes/sample
        # 获取当前帧的二进制数据
        chunk = raw_data[i:i + frame_size * 2]

        # 如果最后一帧不足，补零
        if len(chunk) < frame_size * 2:
            chunk += b'\x00' * (frame_size * 2 - len(chunk))

        # 转换为numpy数组处理
        np_frame = np.frombuffer(chunk, dtype=np.int16)

        # 编码Opus数据
        opus_data = encoder.encode(np_frame.tobytes(), frame_size)
        opus_datas.append(opus_data)

    return opus_datas, duration

async def main():
    server = websockets.serve(send_opus_data, '0.0.0.0', 8765)
    print("WebSocket server started on ws://0.0.0.0:8765")

    # 保持事件循环以避免退出
    async with server:
        await asyncio.Future()  # 运行一个永远不会完成的任务，保持服务器持续运行

asyncio.run(main())
