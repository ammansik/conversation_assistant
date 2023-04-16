import argparse
import asyncio
import sys
import tkinter as tk
import os

import openai
import pyaudio
import speechmatics
import re


def convert_transcript(transcript):
    transcript = (
        transcript.replace(" .", ".")
        .replace(" ,", ",")
        .replace(" ?", "?")
        .replace(" !", "!")
    )
    return transcript


def limit_words(in_text, word_limit):
    words = in_text.split()
    if len(words) > word_limit:
        words = words[:word_limit]
        in_text = " ".join(words)
    return in_text


class AudioProcessor:
    def __init__(self):
        self.wave_data = bytearray()
        self.read_offset = 0

    async def read(self, chunk_size):
        while self.read_offset + chunk_size > len(self.wave_data):
            await asyncio.sleep(0.001)
        new_offset = self.read_offset + chunk_size
        data = self.wave_data[self.read_offset : new_offset]
        self.read_offset = new_offset
        return data

    def write_audio(self, data):
        self.wave_data.extend(data)
        return


class SpeechWindow:
    def __init__(
        self,
        api_key,
        lang_code,
        max_delay,
        chat_prompt,
        device_index,
        chatgpt_word_limit,
    ):
        # setup speech API
        self.setup_speech_api(api_key, lang_code, max_delay)

        # setup audio stream
        self.setup_pyaudio_stream(device_index)

        # setup GUI
        self.setup_gui()

        # Conversation feedback variables
        self.whole_conversation = ""
        self.latest_conversation = ""
        self.chat_prompt = chat_prompt
        self.chatgpgt_word_limit = chatgpt_word_limit

    def setup_gui(self):
        # create your GUI widgets here
        self.root = tk.Tk()
        self.root.geometry("1200x900")
        self.start_button = tk.Button(
            self.root, text="Start recording", command=self.run_start_asr
        )
        self.start_button.pack()

        self.stop_button = tk.Button(
            self.root, text="Stop recording", command=self.run_stop_asr
        )
        self.stop_button.config(state="disabled")
        self.stop_button.pack()

        # create a text box to display the transcription
        self.transcription_text = tk.Text(
            self.root, font=("Helvetica", 16), wrap=tk.WORD, height=10
        )
        self.transcription_text.pack(fill=tk.BOTH, expand=True)

        # create a text box to display feedback from ChatGPT
        self.help_button = tk.Button(self.root, text="Help!", command=self.help)
        self.help_button.pack()

        self.feedback_text = tk.Text(
            self.root, font=("Helvetica", 16), wrap=tk.WORD, fg="red"
        )
        self.feedback_text.pack(fill=tk.BOTH, expand=True)

        self.loop = asyncio.get_event_loop()

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def ask_chatgpt(self):
        self.latest_conversation = limit_words(
            self.latest_conversation, self.chatgpgt_word_limit
        )
        completion = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "user", "content": self.chat_prompt + self.latest_conversation}
            ],
        )
        response = completion.choices[0].message.content
        return response

    async def ask_for_help(self):
        response = await self.loop.run_in_executor(None, self.ask_chatgpt)
        self.feedback_text.delete("1.0", "end")
        self.latest_conversation = ""
        self.feedback_text.insert(tk.END, response)

    def help(self):
        asyncio.create_task(self.ask_for_help())

    def setup_speech_api(
        self, api_key, lang_code, max_delay, operating_point="enhanced"
    ):
        connection_url = f"wss://eu2.rt.speechmatics.com/v2/{lang_code}"
        self.client_running = False

        # Define connection parameters
        conn = speechmatics.models.ConnectionSettings(
            url=connection_url, auth_token=api_key, generate_temp_token=True
        )
        # Create a transcription client
        self.ws = speechmatics.client.WebsocketClient(conn)

        # Define transcription parameters
        # Full list of parameters described here: https://speechmatics.github.io/speechmatics-python/models
        self.transcription_config = speechmatics.models.TranscriptionConfig(
            language=lang_code,
            enable_partials=False,
            max_delay=max_delay,
            operating_point=operating_point,
        )

        # Register the event handler for full transcript
        self.ws.add_event_handler(
            event_name=speechmatics.models.ServerMessageType.AddTranscript,
            event_handler=self.print_transcript,
        )

    def setup_pyaudio_stream(self, device_index, chunk_size=1024):
        self.audio_processor = AudioProcessor()

        # Set up PyAudio
        p = pyaudio.PyAudio()
        if device_index == -1:
            device_index = p.get_default_input_device_info()["index"]
            device_name = p.get_default_input_device_info()["name"]
            DEF_SAMPLE_RATE = int(
                p.get_device_info_by_index(device_index)["defaultSampleRate"]
            )
            print(
                f"***\nIf you want to use a different microphone, update device_index at the start of the code to one of the following:"
            )
            # Filter out duplicates that are reported on some systems
            device_seen = set()
            for i in range(p.get_device_count()):
                if p.get_device_info_by_index(i)["name"] not in device_seen:
                    device_seen.add(p.get_device_info_by_index(i)["name"])
                    try:
                        supports_input = p.is_format_supported(
                            DEF_SAMPLE_RATE,
                            input_device=i,
                            input_channels=1,
                            input_format=pyaudio.paFloat32,
                        )
                    except Exception:
                        supports_input = False
                    if supports_input:
                        print(
                            f"-- To use << {p.get_device_info_by_index(i)['name']} >>, set device_index to {i}"
                        )
            print("***\n")

        SAMPLE_RATE = int(p.get_device_info_by_index(device_index)["defaultSampleRate"])
        device_name = p.get_device_info_by_index(device_index)["name"]

        self.stream = p.open(
            format=pyaudio.paFloat32,
            channels=1,
            rate=SAMPLE_RATE,
            input=True,
            frames_per_buffer=chunk_size,
            input_device_index=device_index,
            stream_callback=self.stream_callback,
        )

        self.audio_settings = speechmatics.models.AudioSettings()
        self.audio_settings.encoding = "pcm_f32le"
        self.audio_settings.sample_rate = SAMPLE_RATE
        self.audio_settings.chunk_size = chunk_size

    async def start_asr(self):
        try:
            self.stream.start_stream()
            await self.ws.run(
                self.audio_processor, self.transcription_config, self.audio_settings
            )
        finally:
            await self.ws.stop()
            await self.loop.shutdown_asyncgens()
            self.loop.stop()

    def run_start_asr(self):
        self.start_button.config(state="disabled")
        self.stop_button.config(state="active")
        if not self.client_running:
            self.client_running = True
            self.loop.create_task(self.start_asr())
        else:
            self.stream.start_stream()

    def run_stop_asr(self):
        self.start_button.config(state="active")
        self.stop_button.config(state="disabled")
        self.stream.stop_stream()

    async def run_gui(self):
        # start the GUI event loop
        while True:
            self.root.update()
            await asyncio.sleep(0.01)

    # PyAudio callback
    def stream_callback(self, in_data, frame_count, time_info, status):
        if in_data:
            self.audio_processor.write_audio(in_data)
        return in_data, pyaudio.paContinue

    def print_transcript(self, msg):
        speech_transcript = msg["metadata"]["transcript"]
        self.latest_conversation += speech_transcript
        self.whole_conversation += speech_transcript
        self.whole_conversation = convert_transcript(self.whole_conversation)

        self.transcription_text.delete("1.0", "end")
        self.transcription_text.insert(tk.END, self.whole_conversation)
        self.transcription_text.see(tk.END)

    def on_closing(self):
        # Do any cleanup or save operations here
        if self.root is not None:
            self.root.destroy()
            self.root = None
        sys.exit()

    def run(self):
        self.loop.create_task(self.run_gui())
        self.loop.run_forever()


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("--lang_code", help="Language code", default="en")
    parser.add_argument(
        "--max_delay",
        help="Max delay (seconds) for speech recogition output",
        default=2.5,
        type=float,
    )
    parser.add_argument(
        "--device_index", help="Audio device index", default=-1, type=int
    )
    parser.add_argument(
        "--chatgpt_word_limit", help="ChatGPT word limit", default=3000, type=int
    )
    parser.add_argument(
        "--chat_prompt",
        help="ChatGPT prompt",
        default="I'm in a job interview. "
        "Please help me out with some questions I'm struggling on. "
        "Always present the answers as short bullet points (max three) for easier readability. "
        "Also keep the language as natural sounding as possible so it's easy to recite.",
    )
    args = parser.parse_args()

    speechmatics_api_key = os.environ.get("SPEECHMATICS_API_KEY")
    if speechmatics_api_key is None:
        raise ValueError("SPEECHMATICS_API_KEY environment variable not set")

    openai.api_key = os.environ.get("CHATGPT_API_KEY")
    if openai.api_key is None:
        raise ValueError("CHATGPT_API_KEY environment variable not set")

    my_app = SpeechWindow(
        speechmatics_api_key,
        args.lang_code,
        args.max_delay,
        args.chat_prompt,
        args.device_index,
        args.chatgpt_word_limit,
    )
    my_app.run()
