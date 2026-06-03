from PIL import Image, ImageDraw, ImageFont

sizes = [256, 128, 64, 48, 32, 16]
images = []

for size in sizes:
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    pad = max(1, size // 10)
    draw.ellipse([pad, pad, size - pad, size - pad], fill=(22, 163, 74, 255))

    font_size = int(size * 0.54)
    font = None
    for path in ["C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/arial.ttf"]:
        try:
            font = ImageFont.truetype(path, font_size)
            break
        except Exception:
            pass
    if not font:
        font = ImageFont.load_default()

    text = "$"
    bb = draw.textbbox((0, 0), text, font=font)
    x = (size - (bb[2] - bb[0])) // 2 - bb[0]
    y = (size - (bb[3] - bb[1])) // 2 - bb[1]
    draw.text((x, y), text, fill=(255, 255, 255, 255), font=font)
    images.append(img)

images[0].save('icone.ico', format='ICO', sizes=[(s, s) for s in sizes], append_images=images[1:])
print("Icone gerado: icone.ico")

import os
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
os.makedirs(static_dir, exist_ok=True)
favicon_img = images[sizes.index(64)]
favicon_img.save(os.path.join(static_dir, 'favicon.png'), format='PNG')
print("Favicon gerado: static/favicon.png")
