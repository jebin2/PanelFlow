from panelflow import config
from .comic_review import ComicReview


class ComicShortsReview(ComicReview):

    def __init__(self, processor_obj):
        super().__init__(processor_obj)
        self.name = config.COMIC_SHORTS

    def get_cred_token_file_name(self):
        return ("ytcredentials.json", "yttoken.json")

    def get_yt_description(self):
        return f"#Comics #Comic #comicbooks #comicbook #comicshorts"

    def get_yt_tags(self):
        return ['Comics', 'Comic', 'comicbooks', 'comicbook', 'comicshorts']

    def get_recap_length(self, type):
        if type == "min":
            return 700
        return 1500
