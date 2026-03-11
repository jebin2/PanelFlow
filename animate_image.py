from moviepy.editor import ImageClip
import numpy as np
import custom_env
import common
from moviepy.editor import VideoFileClip
import moviepy.editor as mpy
from PIL import Image
from custom_logger import logger_config

class ImageAnimator:
    def __init__(self, type, path = None, clip = None, duration = 0, start_time = 0):
        self.path = path
        self.base_clip = clip if clip else ImageClip(path) if type == 'image' else VideoFileClip(path)
        self.duration = duration if type == 'image' else self.base_clip.duration
        self.start_time = start_time
        self.frame = self.base_clip.get_frame(0)
        self.height, self.width = self.frame.shape[:2]
        
    def gentle_ripple(self, origin='center'):
        """Creates a slower, more subtle ripple effect."""
        clip = self.base_clip.copy()
        
        def ripple_transform(get_frame, t):
            frame = get_frame(t)
            height, width = frame.shape[0], frame.shape[1]
            y, x = np.ogrid[:height, :width]

            origin_points = {
                'center': (width/2, height/2),
                'top_left': (0, 0),
                'top_right': (width, 0),
                'bottom_left': (0, height),
                'bottom_right': (width, height)
            }
            origin_x, origin_y = origin_points[origin]
            
            # Calculate distance from center
            dist = np.sqrt((x - origin_x)**2 + (y - origin_y)**2)
            
            # Slower, gentler ripple
            frequency = 2  # Lower frequency for slower ripples
            amplitude = 5   # Smaller amplitude for subtle effect
            ripple = np.sin(dist/20 - frequency*t) * amplitude
            
            # Apply displacement
            x_coords = (x + ripple).clip(0, frame.shape[1]-1).astype(np.int32)
            y_coords = (y + ripple).clip(0, frame.shape[0]-1).astype(np.int32)
            
            return frame[y_coords, x_coords]
            
        clip = clip.fl(ripple_transform)
        return clip.set_duration(self.duration).set_start(self.start_time)

    def diagonal_wave(self, direction='bottom_right_to_top_left', wave_width=100, speed=2, color=(1, 1, 1)):
        clip = self.base_clip.copy()
        valid_directions = {
            'top_left_to_bottom_right': (1, 1),
            'top_right_to_bottom_left': (-1, 1),
            'bottom_left_to_top_right': (1, -1),
            'bottom_right_to_top_left': (-1, -1)
        }

        x_dir, y_dir = valid_directions[direction]

        def wave_transform(get_frame, t):
            frame = get_frame(t)
            height, width = frame.shape[0], frame.shape[1]
            y, x = np.ogrid[:height, :width]
            
            # Adjust coordinates based on direction
            if x_dir < 0:
                x = width - 1 - x
            if y_dir < 0:
                y = height - 1 - y

            # Create a diagonal coordinate system
            # This maps points along the diagonal to similar values
            diagonal_coord = (x + y) / np.sqrt(2)
            
            # Create wave pattern
            wave_phase = diagonal_coord - speed * t * 100
            wave = np.sin(wave_phase / wave_width) * 0.5 + 0.5  # Normalize to 0-1 range
            
            # Create displacement based on wave pattern
            amplitude = 10
            displacement = wave * amplitude
            
            # Apply displacement perpendicular to the diagonal
            # Move points perpendicular to the diagonal direction
            y, x = np.ogrid[:height, :width]
            x_coords = (x + displacement).clip(0, width-1).astype(np.int32)
            y_coords = (y - displacement).clip(0, height-1).astype(np.int32)
            
            # Apply the effect gradually from center of wave
            # This creates a smoother animation
            result = frame[y_coords, x_coords]
            
            # Optional: Add a subtle color modulation to make the wave more visible
            color_modulation = np.stack([wave * color[0], wave * color[1], wave * color[2]], axis=-1) * 0.2 + 0.9
            result = (result * color_modulation).clip(0, 255).astype(np.uint8)
            
            return result
            
        clip = clip.fl(wave_transform)
        return clip.set_duration(self.duration).set_start(self.start_time)

    def create_top_bottom_zoom(self, zoom_height=None):
        """
        Create a top-to-bottom zoom and pan animation for a comic page.
        Maintains original image width while smoothly panning vertically.
        
        Parameters:
        - image_path: Path to the comic page image
        - output_path: Path to save the output video
        - duration: Total animation duration in seconds
        """
        # Load the image
        img = Image.open(self.path)
        width, height = img.size
        
        # Convert to MoviePy clip
        clip = mpy.ImageClip(self.path)
        
        def make_frame(t, zoom_height=zoom_height):
            # Calculate progress (0 to 1)
            progress = t / self.duration
            
            # Calculate the visible height for the zoom window
            # Using 30% of original height for zoom
            if not zoom_height:
                zoom_height = int(height * 0.3)

            # Calculate current vertical position
            # Ensure we don't go past the bottom of the image
            max_y = height - zoom_height
            curr_y = int(progress * max_y)

            # Crop the image to create zoom window
            cropped = clip.crop(
                x1=0,
                y1=curr_y,
                x2=width,
                y2=curr_y + zoom_height
            )

            # Calculate the new height that maintains aspect ratio
            # when scaling back to original width
            new_height = int((zoom_height * width) / width)

            # Resize while maintaining aspect ratio
            resized = cropped.resize((width, new_height))
            
            return resized.get_frame(t)
        
        # Create video clip
        video = mpy.VideoClip(make_frame, duration=self.duration)
        return video

    def create_left_right_zoom(self, zoom_width=None):
        """
        Create a left-to-right zoom and pan animation for a comic page.
        Maintains original image height while smoothly panning horizontally.
        
        Parameters:
        - image_path: Path to the comic page image
        - output_path: Path to save the output video
        - duration: Total animation duration in seconds
        """
        # Load the image
        img = Image.open(self.path)
        width, height = img.size
        
        # Convert to MoviePy clip
        clip = mpy.ImageClip(self.path)
        
        def make_frame(t, zoom_width=zoom_width):
            # Calculate progress (0 to 1)
            progress = t / self.duration
            
            # Calculate the visible width for the zoom window
            # Using 30% of original width for zoom
            if not zoom_width:
                zoom_width = int(width * 0.3)

            # Calculate current horizontal position
            # Ensure we don't go past the right edge of the image
            max_x = width - zoom_width
            curr_x = int(progress * max_x)

            # Crop the image to create zoom window
            cropped = clip.crop(
                x1=curr_x,
                y1=0,
                x2=curr_x + zoom_width,
                y2=height
            )

            # Calculate the new width that maintains aspect ratio
            # when scaling back to original height
            new_width = int((zoom_width * height) / height)

            # Resize while maintaining aspect ratio
            resized = cropped.resize((new_width, height))
            
            return resized.get_frame(t)
        
        # Create video clip
        video = mpy.VideoClip(make_frame, duration=self.duration)
        return video

if __name__ == "__main__":
    clip_info = {
        'img_path': 'media/download.jpg',
        'duration': 10.0,
        "start": 0
    }

    animator = ImageAnimator("image", path=clip_info['img_path'], duration=clip_info['duration'], start_time=clip_info["start"])
    clip = animator.create_top_bottom_zoom()
    output = f"""{custom_env.TEMP_OUTPUT}/{common.generate_random_string()}.mp4"""
    common.write_videofile(clip, output, fps=custom_env.FPS)
    logger_config.info(output)