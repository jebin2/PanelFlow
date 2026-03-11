import json
from custom_logger import logger_config

def get_json_String(value):
    
    def is_whitespace(char):
        return char in [' ', '\t', '\n', '\r']

    value = value.replace('""', "\"")

    final_value = ''

    for i, char in enumerate(value):
        if is_whitespace(char):
            final_value = final_value.strip()
            final_value += " "
            continue

        final_value += char

    try:
        import json_repair
        final_value = json_repair.loads(final_value)
        return json.dumps(final_value, ensure_ascii=False)
    except:
      start_char = None
      start_char_index = -1
      end_char_index = -1
      for i, char in enumerate(final_value):
          if start_char_index == -1 and (char == "[" or char == "{"):
              start_char_index = i
              start_char = char
              end_char = "]" if start_char == "[" else "}"

          elif start_char_index >= 0:
              if end_char == char:
                  end_char_index = i

      final_value = final_value[start_char_index:end_char_index+1]

      logger_config.debug(f'final string from json_parser:get_json_string:: {final_value}')

      return final_value

if __name__ == "__main__":
    test_string = """[
  {
    "key_moment": "\" - You just want me to hit you? - Come on. Do me this one favor.\"",
    "impact": "This exchange marks a turning point in the protagonist's life, introducing Tyler Durden and his philosophy of embracing chaos and self-destruction. The protagonist's willingness to be hit signifies his desire for something more than his mundane existence."
  },
  {
    "key_moment": "\"- I don't know about this. - I don't either.Who gives a shit? No-one's watching. What do you care?\"",
    "impact": "Despite their initial hesitation, the protagonist and Tyler engage in violence, highlighting the absurdity of societal norms and the allure of rebellion. The line 'No-one's watching' underscores their feeling of detachment from conventional values."
  },
  {
    "key_moment": "\"It looked like it was waiting to be torn down. Most of the windows were boarded up. There was no lock on the front door from when the police, or whoever, kicked it in.\"",
    "impact": "The dilapidated house where Tyler lives symbolizes their rejection of societal structures and expectations. The abandoned state of the building reflects their desire to escape the confines of conventional life."
  },
  {
    "key_moment": "\"- Hey, man. What are you reading? - Listen to this. It's an article written by an organ in the first person.\"I am Jack's medulla oblongata. Without me,Jack could not regulate his heart rate or breathing.\"\"",
    "impact": "The introduction of these 'I Am...' articles explores the fragmented nature of identity and consciousness. They suggest that individuals are composed of various parts, each with its own perspective and desires."
  },
  {
    "key_moment": "\"- You could deal with anything. - Have you finished those reports?\"",
    "impact": "This exchange highlights the contrast between Tyler's nihilistic worldview and the protagonist's former life of corporate conformity. The 'reports' symbolize the mundane tasks that once consumed him."
  },
  {
    "key_moment": "\"- He says, \\\"Get a job.\" - Same here.Now I'm 25. Make my yearly call again.\"Dad, now what?\\\"He says, \\\"I dunno. Get married.\"\"",
    "impact": "The protagonist's interactions with his absent father reveal a pattern of emotional neglect and lack of guidance. This fuels his resentment towards societal expectations and reinforces his desire for something more meaningful."
  }
]"""

    import json_repair
    print(json_repair.loads(test_string))