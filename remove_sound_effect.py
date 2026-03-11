from jebin_lib import HFTTTClient
import json_parser
import json_repair

def remove(raw_text):
	raw_text = (
		raw_text
		.replace("\n", "")
		.replace("“", '"')
		.replace("”", '"')
		.replace("‘", "'")
		.replace("’", "'")
	)
	user_prompt = f"""Remove only standalone sound effects, onomatopoeia, and sound effect words from this comic text (like "Splch!", "Hahahah!", "Skrrzk!", "CRACK!", "BANG!", etc.). 

Keep ALL narrative text, dialogue, character names, places, descriptions, and story content intact - even if they describe sounds (like "a sharp crack" or "splattered"). Only remove words that are purely sound effects written as exclamations or onomatopoeia.

Text to clean:
{raw_text}

Return only the cleaned text maintaining original sentence structure and flow. Do not add anything new.

OUTPUT JSON FORMAT:
{{
"cleaned_text":""
}}

Before returning the JSON, verify that you have processed every sentence from the input and that no narrative sentences have been removed."""
	
	hf_ttt_client = HFTTTClient()
	response = hf_ttt_client.generate(user_prompt)
	# Fix any curly quotes that the LLM may have generated in its JSON response
	response = response.replace("“", '"').replace("”", '"')
	
	return json_repair.loads(response)["cleaned_text"]

if __name__ == "__main__":
	# Example usage
	raw_text = "Inside the lab, the Marauders quickly assess their bounty. The armored leader looks at his blue-skinned subordinate and gives the order: “Take what you can. Keep it intact—” The blue mutant points toward one of the stasis pods embedded in the wall. “There’s someone in that one.” The leader, examining the pod’s status indicators, replies with cold detachment, “The pod still has power... doesn’t that mean they’re alive?” The blue mutant, eyes narrowed, challenges him: “Does a corpse frighten you?” Without answering, the leader swiftly fires a sizzling energy beam at an old piece of equipment, causing it to erupt in smoke. He then pulls a burning flare from his belt, casting an anxious light over the cavernous space. “No one’s been down here for ten years. I don’t think they’ll be missed.” But before they can proceed, a massive, bulky shape appears in the gloom of the corridor, its single, large eye glowing an intense, ominous green. The leader turns to his team, readying for confrontation. “I’m only gonna say this once, so open your earholes wide...”"
	print(remove(raw_text))