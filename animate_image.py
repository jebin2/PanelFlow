from moviepy.editor import ImageClip, CompositeVideoClip
from moviepy.video.fx.mirror_x import mirror_x
from moviepy.video.fx.mirror_y import mirror_y
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
        
    def bounce_effect(self):
        """Creates a bouncing animation."""
        clip = self.base_clip.copy()
        
        def bounce_position(t):
            # Create a bouncing motion using sine wave
            bounce_height = 100
            speed = 3
            y_pos = abs(np.sin(speed * np.pi * t)) * bounce_height
            return ('center', 'center'), (0, -y_pos)
            
        return clip.set_position(bounce_position).set_duration(self.duration).set_start(self.start_time)
    
    def spiral_zoom(self):
        """Creates a spiraling zoom effect."""
        clip = self.base_clip.copy()
        
        def spiral_move(t):
            # Create spiral movement
            angle = t * 4 * np.pi
            radius = t * 100
            x = radius * np.cos(angle)
            y = radius * np.sin(angle)
            return ('center', 'center'), (x, y)
            
        def zoom_out(t):
            return max(0.5, 2 - t/self.duration)
            
        clip = clip.resize(zoom_out).set_position(spiral_move)
        return clip.set_duration(self.duration).set_start(self.start_time)
    
    def kaleidoscope(self):
        """Creates a kaleidoscope-like effect."""
        clip = self.base_clip.copy()
        
        def rotate_func(t):
            return 360 * t / self.duration
            
        # Create multiple rotating copies
        clips = []
        for i in range(4):
            rotated = clip.rotate(lambda t: rotate_func(t) + i * 90)
            clips.append(rotated)
            
        # Mirror copies for kaleidoscope effect
        mirrored_clips = []
        for c in clips:
            mirrored_clips.append(mirror_x(c))
            mirrored_clips.append(mirror_y(c))
            
        clips.extend(mirrored_clips)
        
        # Combine all clips
        final = CompositeVideoClip(clips)
        return final.set_duration(self.duration).set_start(self.start_time)
    
    def heartbeat(self):
        """Creates a heartbeat-like pulsing effect."""
        clip = self.base_clip.copy()
        
        def heartbeat_scale(t):
            # Create double-beat effect
            beat_freq = 1.5  # Beats per second
            phase = (t * beat_freq) % 1
            if phase < 0.1:  # First beat
                return 1 + 0.2 * np.sin(phase * np.pi * 10)
            elif 0.2 < phase < 0.3:  # Second beat
                return 1 + 0.15 * np.sin((phase - 0.2) * np.pi * 10)
            return 1
            
        return clip.resize(heartbeat_scale).set_duration(self.duration).set_start(self.start_time)
    
    def ripple(self):
        """Creates a ripple effect."""
        clip = self.base_clip.copy()
        
        def ripple_transform(get_frame, t):
            frame = get_frame(t)
            center_x, center_y = frame.shape[1]/2, frame.shape[0]/2
            y, x = np.ogrid[:frame.shape[0], :frame.shape[1]]
            
            # Calculate distance from center
            dist = np.sqrt((x - center_x)**2 + (y - center_y)**2)
            
            # Create ripple effect
            ripple = np.sin(dist/10 - 5*t) * 10
            
            # Apply displacement
            x_coords = (x + ripple).clip(0, frame.shape[1]-1).astype(np.int32)
            y_coords = (y + ripple).clip(0, frame.shape[0]-1).astype(np.int32)
            
            return frame[y_coords, x_coords]
            
        clip = clip.fl(ripple_transform)
        return clip.set_duration(self.duration).set_start(self.start_time)
    
    def split_slide(self, splits=3):
        """Creates a sliding split effect."""
        clip = self.base_clip.copy()
        clips = []
        
        # Split the image into horizontal strips
        h = clip.h // splits
        for i in range(splits):
            y1, y2 = i*h, (i+1)*h
            strip = clip.crop(y1=y1, y2=y2)
            
            # Alternate direction for each strip
            direction = 1 if i % 2 == 0 else -1
            
            def make_slide(d):
                def slide(t):
                    progress = t / self.duration
                    x = d * 100 * np.sin(progress * np.pi)  # Slide in and out
                    return ('center', y1), (x, 0)
                return slide
            
            strip = strip.set_position(make_slide(direction))
            clips.append(strip)
        
        final = CompositeVideoClip(clips)
        return final.set_duration(self.duration).set_start(self.start_time)
    
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

    def concentric_ripple(self, origin='center'):
        """Creates expanding concentric ripples from the center."""
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

            dist = np.sqrt((x - origin_x)**2 + (y - origin_y)**2)
            
            # Create expanding circles
            speed = 1.5  # Speed of expansion
            frequency = 3  # Number of concurrent ripples
            ripple = np.sin(dist/15 - speed*t * 2*np.pi * frequency) * 8
            
            # Fade ripple strength based on distance from center
            fade_factor = np.exp(-dist/500)  # Adjust 500 to control fade distance
            ripple *= fade_factor
            
            # Apply displacement
            x_coords = (x + ripple).clip(0, frame.shape[1]-1).astype(np.int32)
            y_coords = (y + ripple).clip(0, frame.shape[0]-1).astype(np.int32)
            
            return frame[y_coords, x_coords]
            
        clip = clip.fl(ripple_transform)
        return clip.set_duration(self.duration).set_start(self.start_time)

    def rain_ripple(self):
        """Creates random rain-like ripple effects with fixed broadcasting."""
        clip = self.base_clip.copy()
        
        # Get dimensions from the clip
        frame = clip.get_frame(0)
        height, width = frame.shape[:2]
        
        # Pre-generate random ripple centers
        n_drops = 10
        drop_positions = []
        for _ in range(n_drops):
            x = np.random.rand() * width
            y = np.random.rand() * height
            phase = np.random.rand() * 2 * np.pi
            strength = np.random.rand() * 0.5 + 0.5  # Random strength between 0.5 and 1
            drop_positions.append((x, y, phase, strength))
        
        def ripple_transform(get_frame, t):
            frame = get_frame(t)
            y, x = np.mgrid[0:height, 0:width]
            
            # Initialize displacement map
            ripple = np.zeros((height, width), dtype=float)
            
            # Add effect from each raindrop
            for drop_x, drop_y, phase, strength in drop_positions:
                # Calculate distance from this drop center
                dist = np.sqrt((x - drop_x)**2 + (y - drop_y)**2)
                
                # Create ripple effect with fade over distance
                speed = 2
                amplitude = 3 * strength
                fade_factor = np.exp(-dist/100)  # Fade over distance
                ripple += np.sin(dist/10 - speed*t * 2*np.pi + phase) * amplitude * fade_factor
            
            # Apply displacement
            x_coords = (x + ripple).clip(0, width-1).astype(np.int32)
            y_coords = (y + ripple).clip(0, height-1).astype(np.int32)
            
            return frame[y_coords, x_coords]
            
        clip = clip.fl(ripple_transform)
        return clip.set_duration(self.duration).set_start(self.start_time)

    def pulse_ripple(self):
        """Creates a pulsing ripple effect from the center."""
        clip = self.base_clip.copy()
        
        def ripple_transform(get_frame, t):
            frame = get_frame(t)
            center_x, center_y = frame.shape[1]/2, frame.shape[0]/2
            y, x = np.ogrid[:frame.shape[0], :frame.shape[1]]
            
            # Calculate distance from center
            dist = np.sqrt((x - center_x)**2 + (y - center_y)**2)
            
            # Create pulsing effect
            pulse_speed = 1.0
            pulse_frequency = 0.5
            pulse = np.sin(pulse_speed * t * 2*np.pi) * np.sin(dist/20)
            
            # Add smooth fade based on distance
            fade_factor = np.exp(-dist/300)
            ripple = pulse * fade_factor * 10
            
            # Apply displacement
            x_coords = (x + ripple).clip(0, frame.shape[1]-1).astype(np.int32)
            y_coords = (y + ripple).clip(0, frame.shape[0]-1).astype(np.int32)
            
            return frame[y_coords, x_coords]
            
        clip = clip.fl(ripple_transform)
        return clip.set_duration(self.duration).set_start(self.start_time)

    def directional_ripple(self, angle_degrees=45):
        """Creates a directional wave-like ripple effect."""
        clip = self.base_clip.copy()
        
        def ripple_transform(get_frame, t):
            frame = get_frame(t)
            y, x = np.ogrid[:frame.shape[0], :frame.shape[1]]
            
            # Convert angle to radians
            angle = np.radians(angle_degrees)
            
            # Create directional wave
            wave_length = 30
            speed = 1.5
            amplitude = 6
            
            # Calculate wave based on position and angle
            wave = (x * np.cos(angle) + y * np.sin(angle)) / wave_length - speed * t
            ripple = np.sin(wave * 2*np.pi) * amplitude
            
            # Apply displacement
            x_coords = (x + ripple * np.cos(angle)).clip(0, frame.shape[1]-1).astype(np.int32)
            y_coords = (y + ripple * np.sin(angle)).clip(0, frame.shape[0]-1).astype(np.int32)
            
            return frame[y_coords, x_coords]
            
        clip = clip.fl(ripple_transform)
        return clip.set_duration(self.duration).set_start(self.start_time)

    def matrix_effect(self):
        """Creates a Matrix-style digital rain effect."""
        clip = self.base_clip.copy()
        
        def matrix_transform(get_frame, t):
            frame = get_frame(t)
            y, x = np.mgrid[0:self.height, 0:self.width]
            
            # Create digital rain effect
            rain_speed = 2
            stripe_width = 50
            stripes = np.sin(x/stripe_width + t * rain_speed)
            
            # Add vertical motion
            shift = (t * 100) % self.height
            y_shift = (y + shift).astype(int) % self.height
            
            # Apply green tint and digital effect
            frame = frame.copy()
            frame[:, :, 1] = np.clip(frame[:, :, 1] * (1 + stripes * 0.3), 0, 255)
            return frame[y_shift, x]
        
        clip = clip.fl(matrix_transform)
        return clip.set_duration(self.duration).set_start(self.start_time)

    def pixel_sort(self):
        """Creates a glitch-like pixel sorting effect."""
        clip = self.base_clip.copy()
        
        def sort_transform(get_frame, t):
            frame = get_frame(t)
            
            # Create bands for sorting
            band_height = 50
            num_bands = self.height // band_height
            
            for i in range(num_bands):
                if np.random.random() < 0.5:  # Randomly sort some bands
                    start = i * band_height
                    end = start + band_height
                    band = frame[start:end]
                    
                    # Sort pixels based on brightness
                    brightness = np.mean(band, axis=2)
                    sorted_indices = np.argsort(brightness, axis=1)
                    
                    # Apply sorting with oscillation
                    sort_amount = np.sin(t * 2 + i) * 0.5 + 0.5
                    mask = np.random.random(sorted_indices.shape[0]) < sort_amount
                    
                    for row in range(band.shape[0]):
                        if mask[row]:
                            band[row] = band[row, sorted_indices[row]]
                    
                    frame[start:end] = band
            
            return frame
        
        clip = clip.fl(sort_transform)
        return clip.set_duration(self.duration).set_start(self.start_time)

    def dream_effect(self):
        """Creates a dreamy, flowing effect."""
        clip = self.base_clip.copy()
        
        def dream_transform(get_frame, t):
            frame = get_frame(t)
            y, x = np.mgrid[0:self.height, 0:self.width]
            
            # Create flowing distortion
            flow_speed = 1.5
            flow_scale = 30
            
            distort_x = np.sin(y/flow_scale + t * flow_speed) * 10
            distort_y = np.cos(x/flow_scale + t * flow_speed) * 10
            
            # Apply soft blur effect
            x_coords = (x + distort_x).clip(0, self.width-1).astype(np.int32)
            y_coords = (y + distort_y).clip(0, self.height-1).astype(np.int32)
            
            # Add dreamy color effect
            frame = frame.copy()
            frame = frame.astype(float)
            
            # Soft color manipulation
            frame[:, :, 0] *= 1.1  # Enhance red slightly
            frame[:, :, 2] *= 0.9  # Reduce blue slightly
            
            frame = np.clip(frame, 0, 255).astype(np.uint8)
            return frame[y_coords, x_coords]
        
        clip = clip.fl(dream_transform)
        return clip.set_duration(self.duration).set_start(self.start_time)

    def kaleidoscope(self):
        """Creates a kaleidoscope effect."""
        clip = self.base_clip.copy()
        
        def kaleidoscope_transform(get_frame, t):
            frame = get_frame(t)
            y, x = np.mgrid[0:self.height, 0:self.width]
            
            center_y, center_x = self.height//2, self.width//2
            y = y - center_y
            x = x - center_x
            
            # Calculate radius and angle
            radius = np.sqrt(x**2 + y**2)
            angle = np.arctan2(y, x)
            
            # Create kaleidoscope effect
            n_segments = 8
            angle = (angle + t * 2) % (2 * np.pi / n_segments)
            angle = np.abs(angle - np.pi / n_segments)
            
            # Convert back to coordinates
            x = radius * np.cos(angle) + center_x
            y = radius * np.sin(angle) + center_y
            
            # Clip coordinates
            x = x.clip(0, self.width-1).astype(np.int32)
            y = y.clip(0, self.height-1).astype(np.int32)
            
            return frame[y, x]
        
        clip = clip.fl(kaleidoscope_transform)
        return clip.set_duration(self.duration).set_start(self.start_time)

    def liquid_metal(self):
        """Creates a liquid metal effect with reflection and flow."""
        clip = self.base_clip.copy()
        
        def liquid_transform(get_frame, t):
            frame = get_frame(t)
            y, x = np.mgrid[0:self.height, 0:self.width]
            
            # Create flowing metallic effect
            wave_x = np.sin(x/30 + t*2) * 10
            wave_y = np.cos(y/30 + t*2) * 10
            
            # Add metallic sheen
            shine = np.sin(x/20 - y/20 + t*3) * 0.3 + 0.7
            
            # Apply displacement
            x_coords = (x + wave_x).clip(0, self.width-1).astype(np.int32)
            y_coords = (y + wave_y).clip(0, self.height-1).astype(np.int32)
            
            # Apply metallic effect
            frame = frame.copy()
            frame = frame.astype(float) * shine[:, :, np.newaxis]
            frame = np.clip(frame, 0, 255).astype(np.uint8)
            
            return frame[y_coords, x_coords]
        
        clip = clip.fl(liquid_transform)
        return clip.set_duration(self.duration).set_start(self.start_time)

    def fractal_zoom(self):
        """Creates a fractal-like zooming effect."""
        clip = self.base_clip.copy()
        
        def fractal_transform(get_frame, t):
            frame = get_frame(t)
            y, x = np.mgrid[0:self.height, 0:self.width]
            
            # Create zoom center
            center_y, center_x = self.height//2, self.width//2
            
            # Calculate zoom factor
            zoom = np.exp(t)
            
            # Create fractal-like coordinates
            angle = np.arctan2(y - center_y, x - center_x)
            radius = np.sqrt((x - center_x)**2 + (y - center_y)**2)
            
            # Add spiral effect
            spiral = angle + radius/50 + t*2
            
            # Apply transformation
            x_new = center_x + radius/zoom * np.cos(spiral)
            y_new = center_y + radius/zoom * np.sin(spiral)
            
            # Clip coordinates
            x_new = x_new.clip(0, self.width-1).astype(np.int32)
            y_new = y_new.clip(0, self.height-1).astype(np.int32)
            
            return frame[y_new, x_new]
        
        clip = clip.fl(fractal_transform)
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