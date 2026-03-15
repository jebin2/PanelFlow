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
        return custom_env.COMIC_REVIEW_SYSTEM_PROMPT

    def get_user_prompt(self):
        return custom_env.COMIC_RECAP_USER_PROMPT

    def dialogue_matcher_system_prompt(self):
        return custom_env.COMIC_DIALOGUE_MATCHER_PROMPT

    def title_and_desc_system_prompt(self):
        return custom_env.COMIC_TITLE_DESC_SYSTEM_PROMPT

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
        return "If you want to see what happens next, the next chapter is already up. Go watch it."

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
