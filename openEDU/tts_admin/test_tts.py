import asyncio
import edge_tts
import pygame
import time

TEXT = "你好，這是測試語音，用來確認檔案與播放。"
VOICE = "zh-CN-YunyangNeural"
FILENAME = "test.mp3"

async def main():
    # 1. 生成 TTS 檔案
    print("正在生成 TTS...")
    communicate = edge_tts.Communicate(TEXT, VOICE)
    await communicate.save(FILENAME)
    print(f"✅ 已生成 {FILENAME}，請嘗試雙擊手動播放它")
    
    # 2. Pygame 播放
    print("Pygame 開始播放...")
    pygame.mixer.init()
    pygame.mixer.music.load(FILENAME)
    pygame.mixer.music.play()
    
    # 強制等待播放結束（約 5 秒）
    while pygame.mixer.music.get_busy():
        time.sleep(0.1)
        
    pygame.mixer.quit()
    print("✅ Pygame 播放完畢（若沒聽到聲音，請檢查音量混合器）")

if __name__ == "__main__":
    asyncio.run(main())