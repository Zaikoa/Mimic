import re
import requests

DEEPGRAM_URL = 'https://api.deepgram.com/v1/speak?model=aura-helios-en'
headers = {
    "Authorization": "Token ",
    "Content-Type": "application/json"
}

 # Breaks the sentence into chunks to be fed into the tts method
def segment_text_by_sentence(text):
    sentence_boundaries = re.finditer(r'(?<=[.!?])\s+', text)
    boundaries_indices = [boundary.start() for boundary in sentence_boundaries]
    
    segments = []
    start = 0
    for boundary_index in boundaries_indices:
        segments.append(text[start:boundary_index + 1].strip())
        start = boundary_index + 1
    segments.append(text[start:].strip())

    return segments

# Creats an audio file and continously adds onto it
def synthesize_audio(text, output_file):
    payload = {"text": text}
    with requests.post(DEEPGRAM_URL, stream=True, headers=headers, json=payload) as r:
        for chunk in r.iter_content(chunk_size=1024):
            if chunk:
                output_file.write(chunk)


