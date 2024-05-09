import asyncio
import requests
import websockets
import json
import base64
from phone.completion import is_complete
from phone.prompt import prompt
import os
from dotenv import find_dotenv, load_dotenv

"""
Loads all of the environment variables

Gets messy if you try to store them outside so must be either in directory or in sub directory
"""
load_dotenv(find_dotenv('totallysecret.env'))
DEEPGRAM = os.getenv('DEEPGRAM_API_KEY')
GROQ = os.getenv('GROQ_API')
GPT = os.getenv('GPT_API_KEY')


"""
Collects each part of the user says and creates a transcript

Can also be used to time from first word caught to last
"""
class TranscriptCollector:
    def __init__(self):
        self.reset()
    def reset(self): 
        self.transcript_parts = []

    def add_part(self, part):
        self.transcript_parts.append(part)

    def get_full_transcript(self):
        return ' '.join(self.transcript_parts) # Constructs final sentence 

transcript_collector = TranscriptCollector()

# Connects to the deepgram websocket to send the text through and recieve the audio
def deepgram_connect():
    extra_headers = {'Authorization': 'Token ' + DEEPGRAM}
    deepgram_ws = websockets.connect("wss://api.deepgram.com/v1/listen?encoding=mulaw&sample_rate=8000&endpointing=true", extra_headers = extra_headers)
    
    return deepgram_ws

"""
This takes the twilio websocket, the streamid which is stored inside of the websocket and the text we wish to transmit over the websocket

Audio needs to be encoded with mulaw in order to work and the phone sample rate is always 8000
This can be kept inside of the proxy but in order to decrease complexity it is moved out
"""
async def twilio_sender(twilio_ws, streamsid, text):
        print('twilio_sender started')

        # make a Deepgram Aura TTS request specifying that we want raw mulaw audio as the output
        url = 'https://api.deepgram.com/v1/speak?model=aura-asteria-en&encoding=mulaw&sample_rate=8000&container=none'
        headers = {
            'Authorization': 'Token ' + DEEPGRAM,
            'Content-Type': 'application/json'
        }
        payload = {
            'text': text
        }
        tts_response = requests.post(url, headers=headers, json=payload)

        if tts_response.status_code == 200:
            raw_mulaw = tts_response.content

            # construct a Twilio media message with the raw mulaw
            media_message = {
                'event': 'media',
                'streamSid': streamsid,
                'media': {
                    'payload': base64.b64encode(raw_mulaw).decode('ascii')
                }
            }
            
            # send the TTS audio to the attached phonecall
            await twilio_ws.send(json.dumps(media_message))


"""
This is the proxy that the twilio websocket connects to

The deepgram websocket gets connected and starts listening for audio and sends to deepgram services for a transcription
Deepgram reciever takes in the deepgram websocket and the twilio websocket, deepgram socket retrieves the json response with the transcript attatched
Twilio websocket is used transmit the response from gpt once recieved
"""
async def proxy(client_ws):
    outbox = asyncio.Queue()
    print('started proxy')
    stream_sid = None

    # Connects to the deepgram websocket
    async with deepgram_connect() as deepgram_ws:
        async def deepgram_sender(deepgram_ws):
            print('started deepgram sender')
            while True:
                chunk = await outbox.get()
                await deepgram_ws.send(chunk)

        # passes in deepgram websocket and twilio websocket to transmit and recieve data async
        async def deepgram_receiver(deepgram_ws, client_ws):
            print('started deepgram receiver')
            nonlocal stream_sid
            async for message in deepgram_ws:
                try:
                    dg_json = json.loads(message)
                    sentence = dg_json["channel"]["alternatives"][0]["transcript"] # Whatever deepgram picked up from the call

                    try:
                        if not dg_json["is_final"]: # if not final adds the part to the sentence
                            transcript_collector.add_part(sentence)
                        else:
                            transcript_collector.add_part(sentence) # adds the final piece to the sentence
                            full_sentence = transcript_collector.get_full_transcript()

                            if(is_complete(GROQ, full_sentence.strip()) == "yes"): # asks groq hey is this a good enough sentence to ask gpt
                               # print(f"speaker: {full_sentence}")
                                transcript_collector.reset()

                                response = prompt(full_sentence.strip(), GPT) # passes in that sentence and retrieves response from gpt
                                await twilio_sender(client_ws, stream_sid, response)

                    except:
                        print('did not receive a standard streaming result')
                        continue
                except:
                    print('was not able to parse deepgram response as json')
                    continue
            print('finished deepgram receiver')
            transcript_collector.reset() # if call suddenly cuts out we need to reset the transcript stored

        async def client_receiver(client_ws):
            print('started client receiver')
            nonlocal stream_sid
            # we will use a buffer of 20 messages (20 * 160 bytes, 0.4 seconds) to improve throughput performance
            BUFFER_SIZE = 20 * 160
            buffer = bytearray(b'')
            empty_byte_received = False

            async for message in client_ws:
                try:
                    data = json.loads(message)

                    if data["event"] == "start":
                        print("Media WS: Received event connected or start")
                        stream_sid = data['start']['streamSid'] # needed to send audio through the websocket
                        continue
                    if data["event"] == "media":
                        media = data["media"]
                        chunk = base64.b64decode(media["payload"])
                        buffer.extend(chunk)
                        if chunk == b'':
                            empty_byte_received = True
                    if data["event"] == "stop":
                        print("Media WS: Received event stop")
                        break

                    # check if our buffer is ready to send to our outbox (and, thus, then to deepgram)
                    if len(buffer) >= BUFFER_SIZE or empty_byte_received:
                        outbox.put_nowait(buffer)
                        buffer = bytearray(b'')
                except:
                    print('message from client not formatted correctly, bailing')
                    break

            # if the empty byte was received, the async for loop should end, and we should here forward the empty byte to deepgram
            # or, if the empty byte was not received, but the WS connection to the client (twilio) died, then the async for loop will end and we should forward an empty byte to deepgram
            outbox.put_nowait(b'')
            print('finished client receiver')

        await asyncio.wait([
            asyncio.ensure_future(deepgram_sender(deepgram_ws)),
            asyncio.ensure_future(deepgram_receiver(deepgram_ws, client_ws)),
            asyncio.ensure_future(client_receiver(client_ws))
        ])

        client_ws.close()
        print('finished running the proxy')