from pathlib import Path
import re
from PIL import Image

# 目标目录
img_dir = Path("results/visualizations/ariane133")
output_gif = img_dir / "z_evolution.gif"

pattern = re.compile(r"z_evolution_iter_(\d+)\.png$")

# 收集并按迭代编号排序
frames = []
for path in img_dir.glob("z_evolution_iter_*.png"):
    match = pattern.match(path.name)
    if match:
        iteration = int(match.group(1))
        frames.append((iteration, path))

frames.sort(key=lambda x: x[0])

if not frames:
    raise FileNotFoundError(f"在 {img_dir} 中没有找到 z_evolution_iter_*.png")

# 读取图片
images = [Image.open(path).convert("RGBA") for _, path in frames]

# 保存为 GIF
images[0].save(
    output_gif,
    save_all=True,
    append_images=images[1:],
    duration=200,   # 每帧 200ms，可调
    loop=0,         # 0 表示无限循环
    disposal=2
)

print(f"已生成 GIF: {output_gif}")
print(f"总帧数: {len(images)}")