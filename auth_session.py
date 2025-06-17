from pyrogram import Client

api_id = 26184709
api_hash = 'f6cc16fcdfadbebc6b91cd8cf7f2b375'

with Client('RSIbot', api_id=api_id, api_hash=api_hash) as app:
    print('Готово: сессия сохранена как RSIbot.session')
