from moviepy import VideoClip, AudioClip, concatenate_audioclips, concatenate_videoclips
import numpy as np
from panelflow import config
from jebin_lib import utils
from custom_logger import logger_config

def get_last_valid_frame(clip):
    fps = getattr(clip, 'fps', config.FPS)
    if not fps:
        fps = config.FPS

    t = clip.duration - 1.0 / fps
    while t > 0:
        try:
            return clip.get_frame(t)
        except:
            t -= 1.0 / clip.fps

    return clip.get_frame(min(0, clip.duration-1))


def create_smooth_transition(clip1, clip2, transition_duration=1, transition_type='dissolve'):
    """
    Create a smooth transition between two video clips
    
    Parameters:
    - clip1: First VideoFileClip or ImageClip
    - clip2: Second VideoFileClip or ImageClip
    - transition_duration: Duration of the transition (in seconds)
    - transition_type: Type of transition ('dissolve', 'crossfade', 'wipe')
    
    Returns:
    - Composite VideoClip with smooth transition
    """
    # Ensure clips have the same size
    size = clip1.size
    clip1 = clip1.resized(size)
    clip2 = clip2.resized(size)
    
    def make_transition_frame(t):
        """
        Create transition frame based on selected transition type
        
        Parameters:
        - t: Current time in the transition
        
        Returns:
        - Numpy array representing the transition frame
        """
        # Ensure t is within transition duration
        t = min(t, transition_duration)
        alpha = t / transition_duration
        
        # Get frames from both clips
        # frame1 = clip1.get_frame(min(clip1.duration, t))
        frame1 = get_last_valid_frame(clip1)
        frame2 = clip2.get_frame(0)

        if frame1.ndim == 2:  # Convert grayscale to RGB
            frame1 = np.stack((frame1,) * 3, axis=-1)
        if frame2.ndim == 2:
            frame2 = np.stack((frame2,) * 3, axis=-1)
        
        if transition_type == 'dissolve':
            # Linear dissolve
            return (1 - alpha) * frame1 + alpha * frame2
        
        elif transition_type == 'crossfade':
            # Smooth sine-based crossfade
            smooth_alpha = np.sin(np.pi * alpha / 2) ** 2
            return (1 - smooth_alpha) * frame1 + smooth_alpha * frame2
        
        elif transition_type == 'wipe':
            # Horizontal wipe
            w, h = size
            wipe_width = int(w * alpha)
            
            # Create a composite frame with wipe effect
            composite_frame = frame1.copy()
            composite_frame[:, wipe_width:] = frame2[:, wipe_width:]
            return composite_frame
        
        else:
            # Default to dissolve
            return (1 - alpha) * frame1 + alpha * frame2
    
    # Create transition clip
    transition_clip = VideoClip(make_transition_frame, duration=transition_duration)
    
    return transition_clip

def create_video_with_transitions(clips, transition_duration=1, transition_type='crossfade'):
    """
    Create a video with smooth transitions between clips
    
    Parameters:
    - clips: List of VideoFileClip or ImageClip
    - transition_duration: Duration of each transition
    - transition_type: Type of transition
    
    Returns:
    - Final concatenated video with transitions
    """
    final_clips = []
    silent_audio = AudioClip(lambda t: 0, duration=0.1)
    for i in range(len(clips) - 1):
        temp_audio = clips[i].audio
        if temp_audio:
            temp_audio = temp_audio.subclipped(temp_audio.duration-transition_duration, temp_audio.duration-0.1)

        clips[i] = clips[i].subclipped(0, clips[i].duration-transition_duration)
        # Add first clip
        final_clips.append(clips[i])
        
        # Create and add transition
        transition = create_smooth_transition(
            clips[i], 
            clips[i+1], 
            transition_duration=transition_duration,
            transition_type=transition_type
        )
        if temp_audio:
            extended_audio = concatenate_audioclips([temp_audio, silent_audio])
            transition = transition.with_audio(extended_audio)

        final_clips.append(transition)
    
    # Add final clip
    final_clips.append(clips[-1])
    
    # Concatenate clips
    final_video = concatenate_videoclips(
        final_clips,
        method="chain"
    )
    
    return final_video

# Example usage
def make(clips, transition_duration=1, transition_type="crossfade"):
    # Create your ImageClips
    
    # Available transition types: 
    # 'dissolve', 'crossfade', 'wipe', 'zoom', 'shatter'
    final_video = create_video_with_transitions(
        clips, 
        transition_duration=transition_duration,
        transition_type=transition_type
    )

    return final_video

# Uncomment to run
if __name__ == "__main__":
    from moviepy import VideoFileClip, ImageClip
    clip1 = ImageClip("media/anime/AknXXqpgPc_captioned_anime_review.png").with_duration(2)
    clip2 = ImageClip("media/anime/AnyxNGMDsx_captioned_anime_review.png").with_duration(3)
    clip3 = ImageClip("media/anime/AXHKtwunBw_captioned_anime_review.png").with_duration(2)
    clip4 = ImageClip("media/anime/AKEhQxrRFT_captioned_anime_review.png").with_duration(2)
    clip5 = VideoFileClip(f"CaptionCreator/jhPjBwMSWn.mp4")
    clip6 = VideoFileClip(f"CaptionCreator/ZYGMetYPVU.mp4")

    final_video = make([clip5, clip6])
    output_path = f'{config.TEMP_PATH}/{utils.generate_random_string()}.mp4'
    utils.write_videofile(final_video, output_path)
    logger_config.debug(output_path)