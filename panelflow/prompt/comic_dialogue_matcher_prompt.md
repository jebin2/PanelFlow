Task: ComicPage-Recap Matching

Goal: Match each recap sentence to the single most relevant comic page number.

Matching Rules:
- Every recap sentence must be matched to exactly one comic page number.
- If a sentence spans multiple pages, choose the page where the key action happens.
- Prioritize the page with the most direct story relevance to that sentence.

Output Format (JSON):

{
	"data":[{
		"recap_sentence": "string",
		"comic_page_number": integer
	}]
}
