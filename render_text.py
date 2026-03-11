from PIL import Image, ImageDraw, ImageFont
import gc
import common
from custom_logger import logger_config
import custom_env
from typing import List, Dict

def create_gradient_fill(draw, x: int, y: int, width: int, height: int, start_color: tuple, end_color: tuple) -> None:
    """Create a gradient fill effect for text background."""
    height = int(height)
    for i in range(height):
        r = int(start_color[0] + (end_color[0] - start_color[0]) * i / height)
        g = int(start_color[1] + (end_color[1] - start_color[1]) * i / height)
        b = int(start_color[2] + (end_color[2] - start_color[2]) * i / height)
        draw.line([(x, y + i), (x + width, y + i)], fill=(r, g, b))

def apply_shadow(draw, x: int, y: int, text: str, font: ImageFont.FreeTypeFont, 
                shadow_color: tuple = (0, 0, 0), offset: tuple = (3, 3), 
                shadow_opacity: int = 128) -> None:
    """Apply drop shadow effect to text."""
    # Create shadow with specified opacity
    shadow_color = shadow_color + (shadow_opacity,)
    draw.text((x + offset[0], y + offset[1]), text, font=font, fill=shadow_color)

def create_outline_effect(draw, x: int, y: int, text: str, font: ImageFont.FreeTypeFont, 
                         outline_color: tuple, thickness: int = 2) -> None:
    """Create outline effect around text."""
    for dx in range(-thickness, thickness + 1):
        for dy in range(-thickness, thickness + 1):
            if dx != 0 or dy != 0:
                draw.text((x + dx, y + dy), text, font=font, fill=outline_color)

def apply_text_effects(draw, text: str, x: int, y: int, font: ImageFont.FreeTypeFont, 
                      effects: Dict) -> None:
    """Apply various text effects based on configuration."""
    if effects.get('gradient'):
        bbox = draw.textbbox((x, y), text, font=font)
        gradient_start = effects['gradient'].get('start_color', (255, 0, 0))
        gradient_end = effects['gradient'].get('end_color', (0, 0, 255))
        create_gradient_fill(draw, bbox[0], bbox[1], bbox[2]-bbox[0], bbox[3]-bbox[1], 
                           gradient_start, gradient_end)

    if effects.get('shadow'):
        shadow_config = effects['shadow']
        apply_shadow(draw, x, y, text, font,
                    shadow_color=shadow_config.get('color', (0, 0, 0)),
                    offset=shadow_config.get('offset', (3, 3)),
                    shadow_opacity=shadow_config.get('opacity', 128))

    if effects.get('outline'):
        outline_config = effects['outline']
        create_outline_effect(draw, x, y, text, font,
                            outline_color=outline_config.get('color', (0, 0, 0)),
                            thickness=outline_config.get('thickness', 2))

    # Draw the main text
    text_color = effects.get('color', (255, 255, 255))
    draw.text((x, y), text, font=font, fill=text_color)

def wrap_text(draw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> List[str]:
    """Wrap text into lines based on maximum width."""
    wrapped_lines = []
    lines = text.splitlines()
    
    for line in lines:
        words = line.split()
        current_line = ""
        for word in words:
            test_line = f"{current_line} {word}".strip()
            bbox = draw.textbbox((0, 0), test_line, font=font)
            line_width = bbox[2] - bbox[0]
            if line_width <= max_width:
                current_line = test_line
            else:
                wrapped_lines.append(current_line)
                current_line = word
        wrapped_lines.append(current_line)
    return wrapped_lines

def render_text_block(draw, text_config: Dict, font_size: int, font_path: str, 
                     img_size: tuple, padding: int, extra_space: int, type: str) -> None:
    """Render a block of text with specified styling and effects."""
    position = text_config.get('position', 'middle')
    text_content = text_config.get("text", '')
    font_size_ratio = text_config.get('font_size_ratio', 1.0)
    prefix = text_config.get('prefix', '')
    effects = text_config.get('effects', {})
    
    if not text_content:
        return

    # Configure font
    local_font_size = int(font_size * font_size_ratio)
    local_font = ImageFont.truetype(font_path, local_font_size)
    
    # Calculate dimensions
    img_start_size = img_size[0]
    if type == custom_env.CHESS:
        img_start_size = (img_size[0] - img_size[1]) / 2

    max_width = img_start_size - (2 * padding) - (2 * extra_space)

    # Process text
    full_text = f"{prefix}{text_content}" if prefix else text_content
    wrapped_text = wrap_text(draw, full_text, local_font, max_width)
    
    # Calculate position
    total_height = len(wrapped_text) * (local_font_size + 40)
    if position == 'top':
        y = padding
    elif position == 'bottom':
        y = img_size[1] - total_height - padding
    else:  # middle
        y = (img_size[1] - total_height) / 2

    # Apply alignment
    alignment = text_config.get('alignment', 'center')
    
    # Render each line
    for i, line in enumerate(wrapped_text):
        temp_size = draw.textbbox((0, 0), line, font=local_font)
        text_width = temp_size[2] - temp_size[0]

        if alignment == 'center':
            x = (img_start_size - text_width) / 2
        elif alignment == 'left':
            x = padding + extra_space
        else:  # right
            x = img_start_size - text_width - padding - extra_space

        apply_text_effects(draw, line, x, y + i * (local_font_size + 40), 
                         local_font, effects)

def create_text_image(text_positions: List[Dict], background_path: str, output_path: str, font_path: str, font_size: int = 70, padding: int = 50, extra_space: int = 100, img_size: tuple = custom_env.IMAGE_SIZE, type: str = None):
    background = Image.open(background_path).resize(img_size)
    draw = ImageDraw.Draw(background)

    for text_config in text_positions:
        render_text_block(draw, text_config, font_size, font_path, img_size, padding, extra_space, type)

    if common.file_exists(output_path):
        raise ValueError(f"file already exists:: {output_path}")

    background.save(output_path)
    logger_config.debug(f"""Text image created and saved:: {output_path}""", overwrite=True)
    background.close()
    gc.collect()
    return output_path

if __name__ == "__main__":
    text_positions = [
        {
            "text": "Gradient Title",
            'position': 'top',
            'font_size_ratio': 0.8,
            'alignment': 'center',
            'effects': {
                'gradient': {
                    'start_color': (255, 100, 0),
                    'end_color': (255, 200, 0)
                },
                'shadow': {
                    'color': (0, 0, 0),
                    'offset': (4, 4),
                    'opacity': 160
                }
            }
        },
        {
            "text": "Main Content with Outline",
            'position': 'middle',
            'font_size_ratio': 1.0,
            'alignment': 'center',
            'effects': {
                'outline': {
                    'color': (0, 0, 0),
                    'thickness': 3
                },
                'shadow': {
                    'color': (0, 0, 0),
                    'offset': (4, 4),
                    'opacity': 160
                },
                # 'color': (255, 255, 0)
            }
        },
        {
            "text": "Bottom text with shadow",
            'position': 'bottom',
            'font_size_ratio': 0.6,
            'alignment': 'right',
            'prefix': "Result: ",
            'effects': {
                'shadow': {
                    'color': (0, 0, 0),
                    'offset': (3, 3),
                    'opacity': 128
                },
                # 'color': (0, 255, 255)  # Cyan text
            }
        }
    ]

    
    text_positions = [{
        "text": "thumbnai lText thumbn ailText thumbnailTextthumbnailText thumbnailText thumbnailText thumbnailText",
        'position': 'middle',
        'font_size_ratio': 1.0,
        'alignment': 'center',
        'effects': {
            'shadow': {
                'color': (0, 0, 0),
                'offset': (4, 4),
                'opacity': 160
            }
        }
    }]

    text_positions = [{
        "text": 'Answer at 123.123s',
        'position': 'bottom',
        'alignment': 'center',
        'effects': {
            'shadow': {
                'color': (0, 0, 0),
                'offset': (4, 4),
                'opacity': 160
            }
        }
    }]

    text_positions = [{
        "text": "final_desc",
        'position': 'top',
        'font_size_ratio': 0.6,
        'alignment': 'center',
        'effects': {
            'shadow': {
                'color': (0, 0, 0),
                'offset': (4, 4),
                'opacity': 160
            }
        }
    },{
        "text": "text",
        'position': 'middle',
        'alignment': 'center',
        'effects': {
            'shadow': {
                'color': (0, 0, 0),
                'offset': (4, 4),
                'opacity': 160
            }
        }
    },{
        "text": "final_answer",
        'position': 'bottom',
        'font_size_ratio': 0.6,
        'alignment': 'center',
        'effects': {
            'shadow': {
                'color': (0, 0, 0),
                'offset': (4, 4),
                'opacity': 160
            }
        }
    }]

    output_path = f"{custom_env.TEMP_OUTPUT}/{common.generate_random_string()}.jpg"
    with Image.open("chess/chess_board_with_puzzle.jpg") as background:
        resized_image = background.resize(custom_env.IMAGE_SIZE, Image.LANCZOS)
        resized_image.save(output_path)

    blurred_image = output_path

    text_positions = [{
        "text": 'NF2, RA1\nThank you For Watching.',
        'position': 'middle',
        'alignment': 'center',
        'font_size_ratio': 1,
        'effects': {
                # 'shadow': {
                #     'color': (205, 0, 105),
                #     'offset': (14, 14),
                #     'opacity': 128
                # },
                'color': (108, 92, 231),
                'outline': {
                    'color': (0, 0, 0),
                    'thickness': 10
                },
        }
    }]
    output_path = f"{custom_env.TEMP_OUTPUT}/{common.generate_random_string()}.jpg"
    create_text_image(
        text_positions=text_positions,
        background_path=blurred_image,
        output_path=output_path,
        font_path='Fonts/font_1.ttf',
        padding=200,
        font_size=100,
        img_size=custom_env.IMAGE_SIZE[::-1],
        # type=custom_env.CHESS
    )