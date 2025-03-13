import asyncio
import websockets
import numpy as np
import sounddevice as sd
from opuslib import Decoder
import logging
import time
import threading

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# 音频参数
SAMPLE_RATE = 16000
CHANNELS = 1
FRAME_DURATION = 60  # ms
SAMPLES_PER_FRAME = int(SAMPLE_RATE * FRAME_DURATION / 1000)

class AudioPlayer:
    def __init__(self):
        self.decoder = Decoder(SAMPLE_RATE, CHANNELS)
        self.stream = sd.OutputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=np.int16,
            blocksize=SAMPLES_PER_FRAME * 2,
            latency='high'
        )
        self.stream.start()
        self.buffer = []
        self.lock = threading.Lock()
        self.max_buffer_size = 10  # 约600ms缓冲
        self.play_thread = threading.Thread(target=self._play_loop)
        self.play_thread.daemon = True
        self.play_thread.start()
        
    def _play_loop(self):
        while True:
            if self.buffer:
                with self.lock:
                    data = self.buffer.pop(0)
                try:
                    self.stream.write(data)
                except Exception as e:
                    logging.error(f"播放错误: {e}")
            else:
                time.sleep(0.001)
                
    def play_frame(self, pcm_data):
        try:
            audio_array = np.frombuffer(pcm_data, dtype=np.int16)
            with self.lock:
                if len(self.buffer) < self.max_buffer_size:
                    self.buffer.append(audio_array)
                else:
                    logging.warning("缓冲区已满，丢弃旧帧")
                    self.buffer.pop(0)
                    self.buffer.append(audio_array)
        except Exception as e:
            logging.error(f"数据格式错误: {e}")

    def wait_for_empty(self):
        """等待缓冲区播放完毕"""
        while len(self.buffer) > 0:
            time.sleep(0.1)

    def close(self):
        self.stream.stop()
        self.stream.close()

async def receive_and_play():
    player = AudioPlayer()
    retry_count = 0
    max_retries = 3
    stream_active = True

    while retry_count < max_retries and stream_active:
        try:
            async with websockets.connect(
                'ws://192.168.70.89:8765',
                ping_interval=20,
                ping_timeout=30
            ) as websocket:
                logging.info("成功连接服务器")
                retry_count = 0
                
                while stream_active:
                    try:
                        opus_data = await asyncio.wait_for(
                            websocket.recv(),
                            timeout=5
                        )
                        
                        if opus_data == b'END_OF_STREAM':
                            logging.info("音频流接收完毕")
                            stream_active = False
                            break
                            
                        pcm_frame = player.decoder.decode(opus_data, SAMPLES_PER_FRAME)
                        player.play_frame(pcm_frame)
                        
                    except asyncio.TimeoutError:
                        logging.warning("数据接收超时")
                        break
                        
        except websockets.ConnectionClosed as e:
            if e.code == 1000:
                logging.info("连接正常关闭")
                stream_active = False
            else:
                logging.error(f"连接异常关闭: {e.code} {e.reason}")
                retry_count += 1
                logging.info(f"第{retry_count}次重试...")
                await asyncio.sleep(3)
                
        except Exception as e:
            logging.error(f"连接错误: {str(e)}")
            retry_count += 1
            await asyncio.sleep(3)

    # 优雅关闭
    player.wait_for_empty()
    player.close()
    logging.info("播放器已安全关闭")

if __name__ == "__main__":
    try:
        asyncio.run(receive_and_play())
    except KeyboardInterrupt:
        logging.info("用户主动终止程序")
        