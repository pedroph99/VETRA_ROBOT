"""Synthetic capture conditions and a conservative quality gate for demo photos."""

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageStat


def vary_capture(source, rng):
    image = Image.open(source).convert('RGB')
    image.thumbnail((960, 720))
    width, height = image.size
    light = rng.uniform(.75, 1.25)
    angle = rng.uniform(-6, 6)
    distance = rng.uniform(.9, 1.12)
    blur = rng.uniform(0, .9)
    image = ImageEnhance.Brightness(image).enhance(light)
    if distance > 1:
        crop_w, crop_h = int(width / distance), int(height / distance)
        left, top = (width-crop_w)//2, (height-crop_h)//2
        image = image.crop((left, top, left+crop_w, top+crop_h)).resize((width, height))
    else:
        small = image.resize((int(width*distance), int(height*distance)))
        backdrop = Image.new('RGB', (width, height), image.getpixel((0, 0)))
        backdrop.paste(small, ((width-small.width)//2, (height-small.height)//2))
        image = backdrop
    image = image.rotate(angle, resample=Image.Resampling.BICUBIC,
                         fillcolor=image.getpixel((0, 0)))
    shadow = rng.random() < .3
    if shadow:
        overlay = Image.new('RGB', image.size, (0, 0, 0))
        mask = Image.new('L', image.size)
        draw = ImageDraw.Draw(mask)
        start = rng.randint(0, max(0, width//3))
        draw.polygon([(start, 0), (start+width//3, 0),
                      (start+width//2, height), (start+width//6, height)],
                     fill=rng.randint(35, 75))
        image.paste(overlay, (0, 0), mask)
    occlusion = rng.random() < .12
    if occlusion:
        draw = ImageDraw.Draw(image)
        patch_w = max(1, int(width*rng.uniform(.05, .12)))
        patch_h = max(1, int(height*rng.uniform(.05, .12)))
        x, y = rng.randrange(width), rng.randrange(height)
        draw.ellipse((x, y, x+patch_w, y+patch_h), fill=(47, 74, 37))
    if blur > .12:
        image = image.filter(ImageFilter.GaussianBlur(blur))
    return image, dict(brightness=round(light, 2), angle_degrees=round(angle, 1),
                       distance_factor=round(distance, 2), blur_radius=round(blur, 2),
                       shadow=shadow, occlusion=occlusion)


def assess_quality(image):
    sample = image.convert('L')
    sample.thumbnail((256, 256))
    stats = ImageStat.Stat(sample)
    brightness, contrast = stats.mean[0], stats.stddev[0]
    edge = ImageStat.Stat(sample.filter(ImageFilter.FIND_EDGES)).stddev[0]
    reasons = []
    if brightness < 38 or brightness > 220:
        reasons.append('iluminação')
    if contrast < 18:
        reasons.append('contraste')
    if edge < 10:
        reasons.append('nitidez')
    return dict(accepted=not reasons, brightness=round(brightness, 1),
                contrast=round(contrast, 1), sharpness=round(edge, 1), reasons=reasons)
