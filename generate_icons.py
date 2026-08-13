from PIL import Image, ImageDraw, ImageFont
import os

def create_icon(size, output_path):
    img = Image.new('RGBA', (size, size), (26, 26, 46, 255))
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle([size*0.1, size*0.1, size*0.9, size*0.9], 
                          radius=size*0.15, fill=(15, 52, 96, 255))

    try:
        font = ImageFont.truetype("msyh.ttc", int(size * 0.35))
    except:
        font = ImageFont.load_default()

    text = "3D"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = (size - text_width) / 2 - bbox[0]
    y = (size - text_height) / 2 - bbox[1]
    draw.text((x, y), text, fill=(77, 171, 247, 255), font=font)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    img.save(output_path)
    print(f"Created: {output_path} ({size}x{size})")

create_icon(192, 'static/icons/icon-192.png')
create_icon(512, 'static/icons/icon-512.png')
print("Icons generated successfully!")