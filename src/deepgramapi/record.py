from dotenv import load_dotenv

from deepgram import (
    DeepgramClient,
    LiveTranscriptionEvents,
    LiveOptions,
    Microphone,
)

load_dotenv()

is_finals = []

def record_audio(api_key):
    try:
        deepgram: DeepgramClient = DeepgramClient(api_key)

        dg_connection = deepgram.listen.live.v("1")

        def on_open(self, open, **kwargs):
            print(f"Deepgram Connection Open")

        def on_message(self, result, **kwargs):
            global is_finals
            sentence = result.channel.alternatives[0].transcript
            if len(sentence) == 0:
                return
            if result.is_final:
                is_finals.append(sentence)

                if result.speech_final:
                    utterance = ' '.join(is_finals)
                    print(f"Query: {utterance}")
                    is_finals = []


        def on_metadata(self, metadata, **kwargs):
            print(f"Deepgram Metadata: {metadata}")

        def on_speech_started(self, speech_started, **kwargs):
            print(f"Start recognizing")

        def on_utterance_end(self, utterance_end, **kwargs):
            global is_finals
            if len(is_finals) > 0:
                #utterance = ' '.join(is_finals)
                #print(f"Deepgram Utterance End: {utterance}")
                is_finals = []

        def on_close(self, close, **kwargs):
            print(f"Connection Closed")

        def on_error(self, error, **kwargs):
            print(f"Handled Error: {error}")

        def on_unhandled(self, unhandled, **kwargs):
            print(f"Unhandled Websocket Message: {unhandled}")

        dg_connection.on(LiveTranscriptionEvents.Open, on_open)
        dg_connection.on(LiveTranscriptionEvents.Transcript, on_message)
        #dg_connection.on(LiveTranscriptionEvents.Metadata, on_metadata)
        #dg_connection.on(LiveTranscriptionEvents.SpeechStarted, on_speech_started)
        dg_connection.on(LiveTranscriptionEvents.UtteranceEnd, on_utterance_end)
        dg_connection.on(LiveTranscriptionEvents.Close, on_close)
        dg_connection.on(LiveTranscriptionEvents.Error, on_error)
        dg_connection.on(LiveTranscriptionEvents.Unhandled, on_unhandled)

        options: LiveOptions = LiveOptions(
            model="nova-2",
            language="en-US",
            smart_format=True,
            encoding="linear16",
            channels=1,
            sample_rate=16000,
            interim_results=True,
            utterance_end_ms="1000",
            vad_events=True,
            endpointing=100
        )

        addons = {
            "no_delay": "true"
        }

        print("\n\nPress Enter to stop recording...\n\n")
        if dg_connection.start(options, addons=addons) is False:
            print("Failed to connect to Deepgram")
            return

        microphone = Microphone(dg_connection.send)

        microphone.start()

        input("")

        microphone.finish()

        dg_connection.finish()

        print("Finished")

    except Exception as e:
        print(f"Could not open socket: {e}")
        return