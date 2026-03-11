import common
import custom_env
from PIL import Image, ImageFilter
import numpy as np
import resize_with_aspect
import os

def create_blurred_background(img_clip, coords, duration, resolution):
	"""
	Create a blurred background from the main image using specified coordinates.
	
	Args:
		img_clip: ImageClip of the main image
		coords: (x1, y1, x2, y2) coordinates for the region to expand and blur
		duration: Duration of the clip
		resolution: Target resolution (width, height)
	
	Returns:
		Blurred background clip
	"""
	x1, y1, x2, y2 = coords

	# Crop expanded region
	cropped = img_clip.crop(x1=x1, y1=y1, x2=x2, y2=y2)

	# Blur using Pillow
	def blur_frame(get_frame, t):
		frame = get_frame(t)
		pil_img = Image.fromarray(frame)
		pil_img = pil_img.filter(ImageFilter.GaussianBlur(radius=20))
		return np.array(pil_img)

	blurred = cropped.resize(resolution).fl(blur_frame)
	return blurred.set_duration(duration)

def create_scale_up_clip_multiple(main_image_path, multiple_image_path=None, duration=2, bg_size=custom_env.IMAGE_SIZE, scale_point=0.8, zoom_coords=None, bg_blur=True):
	"""
	Scale up multiple panel images from 90% to 100% of their individual sizes while evenly spreading them in the background.
	Filters images based on width constraints.

	Args:
		multiple_image_path (list): List of image paths.
		duration (float): Clip duration in seconds.
		bg_size (tuple): Background size (width, height).
		scale_point (float): Initial scale factor. If >1.0, zooms in then out.
		zoom_coords (dict): Dictionary with panel-specific zoom coordinates.
						   Format: {panel_index: (x1, y1, x2, y2)}
						   where coordinates are in pixels relative to the original image

	Returns:
		CompositeVideoClip: Combined clip with all scaled panels.
	"""
	from moviepy.editor import ImageClip, CompositeVideoClip

	bg_width, bg_height = bg_size
	
	# Load all images and get their dimensions
	image_data = []
	if multiple_image_path:
		# Step 1: Find largest image (by area or height)
		largest_w, largest_h = 0, 0
		for image_path in multiple_image_path:
			with Image.open(image_path) as img:
				w, h = img.size
				if w * h > largest_w * largest_h:  # compare area
					largest_w, largest_h = w, h
		for image_path in multiple_image_path:
			new_image_path = f'{custom_env.TEMP_OUTPUT}/{os.path.basename(image_path)}'
			resize_with_aspect.scale_keep_ratio(image_path, largest_w, largest_h, output_path=new_image_path)
			panel = ImageClip(new_image_path).set_duration(duration)
			img_width, img_height = panel.size
			image_data.append((new_image_path, panel, img_width, img_height))

	if main_image_path:
		# First check if the main image_path is 80-90% of background width
		main_image_panel = ImageClip(main_image_path).set_duration(duration)
		main_img_width, main_img_height = main_image_panel.size
		main_width_ratio = main_img_width / bg_width
	
		# if 0.7 <= main_width_ratio <= 1.5:
		if not image_data:
			# Use only the main image_path
			image_data = [(main_image_path, main_image_panel, main_img_width, main_img_height)]

	# Calculate total original width
	total_original_width = sum(img_width for _, _, img_width, _ in image_data)
	
	# Check if total width exceeds background width
	if total_original_width > bg_width:
			# Remove images from multiple_image_path until total width fits
			# image_data.sort(key=lambda x: x[2], reverse=True)  # Sort by width, largest first
			filtered_images = []
			current_total_width = 0
			
			for img_path, panel, img_width, img_height in image_data:
				if current_total_width + img_width <= bg_width:
					filtered_images.append((img_path, panel, img_width, img_height))
					current_total_width += img_width
			
			image_data = filtered_images if filtered_images else image_data
	
	# Continue with the filtered images
	panel_clips = []
	
	# Create blurred background if blur_coords and main_image_path are provided
	background_clips = []
	if main_image_path and 0 in zoom_coords:
		main_image_clip = ImageClip(main_image_path).set_duration(duration)
		if bg_blur:
			blurred_bg = create_blurred_background(main_image_clip, zoom_coords[0], duration, bg_size)
			background_clips.append(blurred_bg)
		else: background_clips.append(main_image_clip)
	
	total_original_width = sum(img_width for _, _, img_width, _ in image_data)
	max_original_height = max(img_height for _, _, _, img_height in image_data)

	# Compute scale factor to fit all panels horizontally in background
	scale_to_fit_all = min(bg_width / total_original_width, bg_height / max_original_height)

	# Calculate total scaled width of all images
	total_scaled_width = sum(img_width * scale_to_fit_all for _, _, img_width, _ in image_data)

	# Compute horizontal gap to evenly spread panels
	num_gaps = len(image_data) + 1  # gaps between images and at the edges
	gap_size = (bg_width - total_scaled_width) / num_gaps
	delay_per_panel = 0  # 0.5s delay between each panel
	panel_index = 0
	
	# Start placing panels
	current_x = gap_size  # Start after first gap
	for image_path, panel, img_width, img_height in image_data:
		# Start at 90% of fit, grow to 100%
		def scale_func(t, scale=scale_to_fit_all, delay=0.5):
			progress = max(0, t - delay) / duration  # delay shrink start
			progress = min(progress, 1)  # clamp progress to 1
			# progress = t / duration  # 0 → 1
			if scale_point <= 1.0:
				return scale * (scale_point + (1-scale_point) * progress)
			return scale * (scale_point - (scale_point - 1) * progress)

		delay = panel_index * delay_per_panel
		# Resize dynamically
		scaled_panel = panel.resize(
			lambda t, scale=scale_to_fit_all, delay=delay: scale_func(t, scale, delay)
		)

		# Get zoom coordinates for this panel (default to center if not specified)
		if zoom_coords and panel_index in zoom_coords:
			x1, y1, x2, y2 = zoom_coords[panel_index]
			# Convert pixel coordinates to center ratios
			zoom_x_ratio = (x1 + x2) / (2 * img_width)
			zoom_y_ratio = (y1 + y2) / (2 * img_height)
			# Clamp to valid range
			zoom_x_ratio = max(0.0, min(1.0, zoom_x_ratio))
			zoom_y_ratio = max(0.0, min(1.0, zoom_y_ratio))
		else:
			zoom_x_ratio, zoom_y_ratio = 0.5, 0.5  # Default to center
		
		# Set dynamic position with custom zoom coordinates
		def get_position(t, base_x=current_x, panel_idx=panel_index, 
						img_w=img_width, img_h=img_height, 
						zoom_x_r=zoom_x_ratio, zoom_y_r=zoom_y_ratio):
			
			current_scale = scale_func(t)
			scaled_width = img_w * current_scale
			scaled_height = img_h * current_scale
			
			if scale_point > 1.0:
				# When zooming out from initial zoom
				progress = max(0, t - delay) / duration
				progress = min(progress, 1)
				
				# Calculate zoom offset based on custom coordinates
				# At t=0 (zoomed in), we want to show the specified region
				# At t=duration (zoomed out), we want to show the center
				
				# Maximum offset when fully zoomed in
				max_x_offset = (scaled_width - img_w * scale_to_fit_all) * (zoom_x_r - 0.5)
				max_y_offset = (scaled_height - img_h * scale_to_fit_all) * (zoom_y_r - 0.5)
				
				# Interpolate offset from max to 0 as we zoom out
				current_x_offset = max_x_offset * (1 - progress)
				current_y_offset = max_y_offset * (1 - progress)
				
				# Final position
				final_x = base_x + (img_w * scale_to_fit_all - scaled_width) / 2 - current_x_offset
				final_y = (bg_height - scaled_height) / 2 - current_y_offset
			else:
				# Original centering logic for scale_point <= 1.0
				final_x = base_x + (img_w * scale_to_fit_all - scaled_width) / 2
				final_y = (bg_height - scaled_height) / 2
			
			return (final_x, final_y)

		scaled_panel = scaled_panel.set_pos(get_position)
		panel_clips.append(scaled_panel)
		panel_index += 1

		# Update X position for next image (add gap)
		scaled_width = img_width * scale_to_fit_all
		current_x += scaled_width + gap_size

	# Combine blurred background + all scaled panels into one clip
	all_clips = background_clips + panel_clips
	composite_clip = CompositeVideoClip(all_clips, size=bg_size, bg_color=(0, 0, 0))

	return composite_clip

if __name__ == "__main__":
	# Example run with custom zoom coordinates using x1, y1, x2, y2
	zoom_coordinates = {
		0: (0, 112, 1920, 163),   # First panel: focus on region from (50,100) to (300,400)
		1: (200, 300, 450, 600),  # Second panel: focus on region from (200,300) to (450,600)
		2: (1000, 50, 1100, 250),   # Third panel: focus on region from (100,50) to (350,250)
		3: (1000, 50, 1100, 250),   # Third panel: focus on region from (100,50) to (350,250)
		4: (1000, 50, 1100, 250),   # Third panel: focus on region from (100,50) to (350,250)
		5: (1000, 50, 1100, 250),   # Third panel: focus on region from (100,50) to (350,250)
		# Panels not specified will use default center
	}

	common.write_videofile(
		create_scale_up_clip_multiple(
			'reuse/comic_review_Sonja Reborn #2 (2025)/split_0002/0015_panel_(2, 359, 675, 3022).jpg',
			[
				
			'reuse/comic_review_Sonja Reborn #2 (2025)/split_0002/0003_panel_(1127, 1616, 1473, 3056).jpg',
			'reuse/comic_review_Sonja Reborn #2 (2025)/split_0002/0015_panel_(2, 359, 675, 3022).jpg',
			# 	'reuse/comic_review_Sonja Reborn #2 (2025)/split_0002/0002_panel_(1525, 1636, 1917, 3056).jpg',
			# 	'reuse/comic_review_Bloodletter #1 (2025)/split_0015/panel_2_(73, 1402, 508, 2989).jpg',
			# 	'reuse/comic_review_Bloodletter #1 (2025)/split_0015/panel_3_(539, 1402, 955, 2989).jpg',
			# 	'reuse/comic_review_Bloodletter #1 (2025)/split_0015/panel_4_(987, 1402, 1402, 2989).jpg',
			# 	'reuse/comic_review_Bloodletter #1 (2025)/split_0015/panel_5_(1432, 1402, 1848, 2989).jpg'
			],
			duration=5,
			bg_size=custom_env.IMAGE_SIZE,
			scale_point=0.5,  # Scale > 1.0 for zoom in then out
			zoom_coords={
		        0: (0, 0, custom_env.IMAGE_SIZE[0], custom_env.IMAGE_SIZE[1]),
		        1: (0, 0, custom_env.IMAGE_SIZE[0], custom_env.IMAGE_SIZE[1]),
		        2: (0, 0, custom_env.IMAGE_SIZE[0], custom_env.IMAGE_SIZE[1])
            }
		),
		"text_output.mp4"
	)