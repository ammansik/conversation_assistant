# Conversation assistant
A GUI for a real-time conversation assistant, powered by ChatGPT and Speechmatics API.

Use real-time speech recognition to record conversations and query ChatGPT with a suitable prompt to get help.

```console
pip3 install -r requirements.txt
export SPEECHMATICS_API_KEY=<api_key>
export CHATGPT_API_KEY=<api_key>
python3 speech_window.py \
    --lang_code <LANG_CODE> \
    --chat_prompt <CHAT_PROMPT>
```


