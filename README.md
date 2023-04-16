# Conversation assistant
A GUI for a real-time conversation assistant, powered by [ChatGPT](https://openai.com/blog/chatgpt) and [Speechmatics API](https://www.speechmatics.com).

Use real-time speech recognition to record conversations and query ChatGPT with an in-context prompt to get help.

```console
pip3 install -r requirements.txt
export SPEECHMATICS_API_KEY=<api_key>
export CHATGPT_API_KEY=<api_key>
python3 conversation_assistant.py \
    --lang_code <LANG_CODE> \
    --chat_prompt <CHAT_PROMPT>
```


