from asyncio import sleep
from secrets import token_hex

from bot import multi_tags, download_dict_lock
from bot.helper.ext_utils.bulk_links import extract_bulk_links
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.message_utils import send_message, sendStatusMessage



async def remove_from_same_dir(mid, sameDir, folder_name):
        async with download_dict_lock:
            if (
                folder_name
                and sameDir
                and mid in sameDir[folder_name]["tasks"]
            ):
                sameDir[folder_name]["tasks"].remove(mid)
                sameDir[folder_name]["total"] -= 1
            return sameDir

async def run_multi(client, message, obj, input_list, isQbit, isLeech, sameDir, bulk, vidMode, multi_tag, options, multi):
        try:
            await sleep(7)
            if not multi_tag and multi > 1:
                multi_tag = token_hex(3)
                multi_tags.add(multi_tag)
            elif multi <= 1:
                if multi_tag in multi_tags:
                    multi_tags.discard(multi_tag)
                return
            if multi_tag and multi_tag not in multi_tags:
                await send_message(
                    message, f"{message.from_user.mention} Multi Task has been cancelled!"
                )
                await sendStatusMessage(message)
                async with download_dict_lock:
                    for fd_name in sameDir:
                        sameDir[fd_name]["total"] -= multi
                return
            if len(bulk) != 0:
                msg = input_list[:1]
                msg.append(f"{bulk[0]} -i {multi - 1} {options}")
                msgts = " ".join(msg)
                if multi > 2:
                    msgts += f"\n• <b>Cancel Multi:</b> <i>/{BotCommands.CancelMirror[1]}_{multi_tag}</i>"
                nextmsg = await send_message(message, msgts)
            else:
                msg = [s.strip() for s in input_list]
                index = msg.index("-i")
                msg[index + 1] = f"{multi - 1}"
                nextmsg = await client.get_messages(
                    chat_id=message.chat.id,
                    message_ids=message.reply_to_message_id + 1,
                )
                msgts = " ".join(msg)
                if multi > 2:
                    msgts += f"\n• <b>Cancel Multi:</b> <i>/{BotCommands.CancelMirror[1]}_{multi_tag}</i>"
                nextmsg = await send_message(nextmsg, msgts)
            nextmsg = await client.get_messages(chat_id=message.chat.id, message_ids=nextmsg.id)
            if message.from_user:
                nextmsg.from_user = message.from_user
            else:
                nextmsg.sender_chat = message.sender_chat
            await obj(
                client,
                nextmsg,
                isQbit,
                isLeech,
                sameDir,
                bulk,
                vidMode=vidMode,
                multi_tag=multi_tag,
                options=options,
            )
        except Exception as e:
            await send_message(message, str(e))
            return 
    
async def init_bulk(client, message, obj, input_list, isQbit, isLeech, sameDir, bulk, vidMode, multi_tag, options, bulk_start, bulk_end):
        try:
            bulk = await extract_bulk_links(message, bulk_start, bulk_end)
            if len(bulk) == 0:
                raise ValueError("Bulk Empty!")
            b_msg = input_list[:1]
            options = input_list[1:]
            index = options.index("-b")
            del options[index]
            if bulk_start or bulk_end:
                del options[index + 1]
            options = " ".join(options)
            b_msg.append(f"{bulk[0]} -i {len(bulk)} {options}")
            msg = " ".join(b_msg)
            if len(bulk) > 2:
                multi_tag = token_hex(3)
                multi_tags.add(multi_tag)
                msg += f"\n• <b>Cancel Multi:</b> <i>/{BotCommands.CancelMirror[1]}_{multi_tag}</i>"
            nextmsg = await send_message(message, msg)
            nextmsg = await client.get_messages(
                chat_id=message.chat.id, message_ids=nextmsg.id
            )
            if message.from_user:
                nextmsg.from_user = message.from_user
            else:
                nextmsg.sender_chat = message.sender_chat
            _mirror_leech(client, nextmsg, isQbit, isLeech, sameDir, bulk)

            obj(
                client,
                nextmsg,
                isQbit,
                isLeech,
                sameDir,
                bulk,
                vidMode=vidMode,
                multi_tag=multi_tag,
                options=options,
            )
        except Exception:
            await send_message(
                message,
                "Reply to text File or to telegram message that have links seperated by new line!",
            )

