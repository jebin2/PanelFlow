from PIL import Image, ImageFilter
import os

def scale_keep_ratio(image_path, target_width, target_height, output_path=None, fill=False, blur_bg=False):
    """
    Resize an image while keeping aspect ratio.
    - If fill=False: fits entirely within the target box (no cropping).
    - If fill=True: fills the target box completely (may crop some parts).
    """
    img = Image.open(image_path).convert("RGBA")
    iw, ih = img.size
    image_aspect = iw / ih
    target_aspect = target_width / target_height

    if fill:
        # Scale to fill the box, crop excess
        if image_aspect > target_aspect:
            scale = target_height / ih
        else:
            scale = target_width / iw
    else:
        # Scale to fit within box, no cropping
        if image_aspect > target_aspect:
            scale = target_width / iw
        else:
            scale = target_height / ih

    new_w, new_h = int(iw * scale), int(ih * scale)
    resized = img.resize((new_w, new_h), Image.LANCZOS)

    # Create background (blurred or plain black)
    if blur_bg:
        bg = img.resize((target_width, target_height), Image.LANCZOS)
        bg = bg.filter(ImageFilter.GaussianBlur(radius=50))

        if bg.mode != "RGBA":
            bg = bg.convert("RGBA")
        if resized.mode != "RGBA":
            resized = resized.convert("RGBA")

        x = (target_width - new_w) // 2
        y = (target_height - new_h) // 2
        bg.paste(resized, (x, y), resized)
        resized = bg

    if output_path is None:
        base, ext = os.path.splitext(image_path)
        suffix = "_scaled_fill" if fill else "_scaled_fit"
        output_path = f"{base}{suffix}{ext}"

    # ✅ Convert back to RGB if saving as JPEG
    if output_path.lower().endswith((".jpg", ".jpeg")) and resized.mode == "RGBA":
        resized = resized.convert("RGB")

    resized.save(output_path)
    print(f"✅ Saved resized image: {output_path} ({resized.size[0]}x{resized.size[1]})")

if __name__ == "__main__":
    path = "test_images/X-Men United 001 (2026) - 0003.jpg"
    width = 1920
    height = 1080
    output_path = "temp/output.jpg"
    scale_keep_ratio(
        path,
        width,
        height,
        output_path,
        blur_bg=False
    )
