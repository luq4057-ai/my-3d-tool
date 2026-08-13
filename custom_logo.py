"""
自定义 PWA 图标生成器
使用方法：将您的 logo.png 放在项目根目录，然后运行此脚本
"""
from PIL import Image, ImageDraw
import os

def create_rounded_icon(input_path, output_path, size):
    """创建圆角图标"""
    img = Image.open(input_path).convert('RGBA')
    img = img.resize((size, size), Image.LANCZOS)

    mask = Image.new('L', (size, size), 0)
    draw = ImageDraw.Draw(mask)
    radius = size // 5
    draw.rounded_rectangle([0, 0, size-1, size-1], radius=radius, fill=255)

    result = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    result.paste(img, (0, 0), mask)
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    result.save(output_path)
    print(f"✅ 已生成: {output_path} ({size}x{size})")

if __name__ == "__main__":
    logo_path = "logo.png"
    
    if not os.path.exists(logo_path):
        print(f"❌ 未找到 {logo_path}")
        print("请将您的 logo.png 放在项目根目录后重新运行")
    else:
        create_rounded_icon(logo_path, "static/icons/icon-192.png", 192)
        create_rounded_icon(logo_path, "static/icons/icon-512.png", 512)
        print("\n🎉 图标生成完成！")
        print("现在可以重新添加到手机主屏幕，图标将显示您的 logo")