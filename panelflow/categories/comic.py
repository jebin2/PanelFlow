import json_repair

from google import genai
from pydantic import BaseModel

from .base import CategoryBase
from panelflow import config as custom_env
from panelflow import common


class DataFormat(BaseModel):
    data: str


class titleAndDescription(BaseModel):
    youtube_title: str
    twitter_post: str


class Comic(CategoryBase):

    def __init__(self, processor_obj):
        super().__init__(custom_env.COMIC, processor_obj)

    def get_fyi(self, file_base_name_without_ext):
        return f'This is an Comic panel from the comic called {file_base_name_without_ext}'

    def get_cred_token_file_name(self):
        return ("ytcredentials.json", "yttoken.json")

    def get_yt_description(self):
        return (
            "Join me as we break down the latest comics, diving deep into its themes, "
            "character development, and key plot points.\n\n"
            "#comics #ComicBreakdown #ComicAnalysis #ComicReview #ComicNarration #ComicStorytelling"
        )

    def get_yt_tags(self):
        return ['ComicBreakdown', 'ComicAnalysis', 'ComicReview', 'ComicNarration', 'ComicStorytelling', 'comics']

    def get_recap_length(self, type):
        if type == "min":
            return 0
        return 10000000000000000

    # ------------------------------------------------------------------ prompts

    def review_system_prompt(self):
        return """You are an engaging comic narrator, skilled at transforming comic chapters into immersive storytelling content for YouTube. Your job is to:

### 🎬 Transform Comic Panels Into Narrative Storytelling

* Convert visual panels into vivid, flowing narration.
* Focus on **story-relevant content only**, including:

  * Key plot points and major developments
  * Character actions, dialogue, and meaningful interactions
  * Visual cues that drive the story (e.g. setting, props, expressions)
  * Scene atmosphere and tone

### 🎙 Maintain Immersive, Natural Storytelling

* Use a **conversational, emotionally resonant style**
* Describe character **expressions, tone of voice, and emotional shifts**
* Create atmosphere through descriptive language and mood-setting details
* Adapt tone to match each scene: **dramatic, intense, comedic, or heartfelt**
* Distinguish characters with **unique vocal styles or descriptors** where appropriate
* Avoid all sound effects, onomatopoeia, or audio cues - focus purely on narrative description

### 🧭 Ensure Seamless Narrative Flow

* Narrate as **one continuous story** — no references to panels, pages, or transitions
* Keep pacing tight and focused, matching story beats
* Avoid any mention of publishing info, credits, or metadata

### 🎧 Keep the YouTube Audience Engaged

* Use **dynamic, cinematic descriptions** that complement what viewers see
* Balance action, dialogue, and quiet moments for emotional impact
* Set scenes clearly, but concisely — **let mood and moment lead**
* Make viewers feel invested in the characters and their journey
* Write only speakable content that flows naturally when read by TTS systems

Response ONLY IN JSON FORMAT:
{
\t"data":""
}
"""

    def get_user_prompt(self):
        return """Transform these comic pages into a dynamic 1 minute Recap.

Recap Text Requirements:

Start with a powerful 1-2 sentence hook
Analyze main narrative content only
Focus on key plot points, dramatic moments within the core story, clear and punchy sentences that sound natural when read aloud
Avoid complex words or phrases that might trip up TTS engines
Build tension through pacing and word choice
MUST be 1 minute when read at natural speaking pace
Include clear beginning, middle, and end
Use engaging, present-tense narrative style
Maintain suspense and viewer interest
Length guideline: 1 minute duration
Include natural pauses and breathing room (using punctuation like ..., —, !)

Write in a style that balances descriptive storytelling with fast-paced energy suitable for Shorts.

VALIDATION STEPS:
Make sure recap is 1 minute duration
Confirm focus on core narrative only"""

    def dialogue_matcher_system_prompt(self):
        return """Task: ComicPage-Recap Matching

Goal: Match recap/summary sentences to their most relevant source Comic Page. Each recap sentence must be paired with at least one corresponding Comic Page excerpt.

Matching Rules:
- Every recap sentence must have at least one Comic Page match.
- Prioritize the most relevant Comic Page for each recap.

Output Format (JSON):

{
\t"data":[{
\t\t"recap_sentence": "string",
\t\t"comic_page_number": "string"
\t}]
}"""

    def title_and_desc_system_prompt(self):
        return """# Social Media Content Creator

Create engaging YouTube titles and Twitter posts that get clicks and engagement.

## Output Format
```json
{
\t"youtube_title": "Your title here",
\t"twitter_post": "Your post here"
}
```

## YouTube Title Rules
- **Max 100 characters** (best: 60-70)
- Use casual, conversational tone
- Create curiosity without revealing everything
- **Never mention movie names** - keep them mysterious
- **Never use words**: "review", "recap", "breakdown"
- Use hooks like: "This comic changed everything", "You won't believe what happens"
- Include emotional triggers: "shocking", "unexpected", "incredible", "mind-blowing"

## Twitter Post Rules
- **Max 280 characters**
- Add 1-2 emojis, 2-3 hashtags
- **Absolutely NO link references**
- Write complete standalone thoughts

## Exclude
- **Never mention movie/comic/anime names**
- **Never use words**: "review", "recap", "breakdown", "analysis"
"""

    def title_desc_user_prompt(self):
        return "Create a suitable youtube title and twitter post for the above."

    def title_desc_schema(self):
        return genai.types.Schema(
            type=genai.types.Type.OBJECT,
            required=["youtube_title", "twitter_post"],
            properties={
                "youtube_title": genai.types.Schema(type=genai.types.Type.STRING),
                "twitter_post": genai.types.Schema(type=genai.types.Type.STRING),
            },
        )

    def recap_schema(self):
        return genai.types.Schema(
            type=genai.types.Type.OBJECT,
            required=["data"],
            properties={"data": genai.types.Schema(type=genai.types.Type.STRING)},
        )

    def dialogue_matcher_schema(self):
        return genai.types.Schema(
            type=genai.types.Type.OBJECT,
            required=["data"],
            properties={
                "data": genai.types.Schema(
                    type=genai.types.Type.ARRAY,
                    items=genai.types.Schema(
                        type=genai.types.Type.OBJECT,
                        required=["comic_page_number", "recap_sentence"],
                        properties={
                            "comic_page_number": genai.types.Schema(type=genai.types.Type.INTEGER),
                            "recap_sentence": genai.types.Schema(type=genai.types.Type.STRING),
                        },
                    ),
                )
            },
        )

    def get_recap_match_user_prompt(self, recap_text):
        return f"""Recap: {recap_text}

For each sentence in the "Recap" find ONE exact or most suitable comic page.

OUTPUT FORMAT:
{{
\t"data":[{{
\t\t"recap_sentence":"<sentence from Recap>",
\t\t"comic_page_number":"<comic_page_number>"
\t}}]
}}"""

    def get_welcome_phrase(self):
        return ''

    def get_finish_phrase(self):
        return "Thanks for tuning in. Stay curious, stay awesome, and don't forget to hit that subscribe button for more amazing content"

    # ------------------------------------------------------------------ helpers

    def parse_content(self, content):
        try:
            data = json_repair.loads(content)
            if "moments" in data:
                return data["moments"]
            return data
        except Exception:
            raise ValueError("LLM failed to correct the data")

    def retry(self, recap, geminiWrapper, key):
        if len(recap) > self.get_recap_length("max") or len(recap) < self.get_recap_length("min"):
            for i in range(5):
                model_responses = geminiWrapper.send_message(
                    user_prompt="Please try again, duration did not meet the criteria."
                )
                new_recap = ""
                for model_res in model_responses:
                    local_recap = self.parse_content(model_res)[key]
                    new_recap += f" {local_recap}"
                if len(new_recap) <= self.get_recap_length("max") and len(new_recap) > len(recap):
                    recap = new_recap
                if len(new_recap) <= self.get_recap_length("max") and len(new_recap) >= self.get_recap_length("min"):
                    recap = new_recap
                    break
        return utils.clean_text(recap)
