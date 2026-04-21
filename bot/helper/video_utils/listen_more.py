from pyrogram import filters

# Track users waiting for convert input
convert_waiting_users = {}  # {user_id: executor_data}

@bot.on_message(filters.text & filters.private)
async def handle_convert_input(client, message: Message):
    """Handle user text input for convert parameters"""
    user_id = message.from_user.id
    
    # Check if user has active convert waiting
    if user_id not in convert_waiting_users:
        return
    
    executor_data = convert_waiting_users[user_id]
    
    if executor_data.get('stage') != 'waiting_input':
        return
    
    waiting_for = executor_data.get('waiting_for', {})
    param_type = waiting_for.get('type')  # 'video', 'audio', 'subtitle'
    param_name = waiting_for.get('param')
    user_input = message.text.strip()
    
    try:
        # Validate and store input based on parameter type
        if param_name == 'crf':
            value = int(user_input)
            if not 0 <= value <= 51:
                await message.reply('❌ CRF must be between 0 and 51!')
                return
            executor_data['video_settings']['crf'] = str(value)
            await message.reply(f'✓ CRF set to {value}')
        
        elif param_name == 'bitrate':
            # Validate bitrate format (e.g., 2M, 5000k, 128k)
            if not any(user_input.endswith(x) for x in ['k', 'K', 'm', 'M']):
                await message.reply('❌ Bitrate must end with k or M (e.g., 2M, 5000k)')
                return
            if param_type == 'video':
                executor_data['video_settings']['bitrate'] = user_input
            else:
                executor_data['audio_settings']['bitrate'] = user_input
            await message.reply(f'✓ Bitrate set to {user_input}')
        
        elif param_name == 'fps':
            value = int(user_input)
            if value < 1 or value > 120:
                await message.reply('❌ FPS must be between 1 and 120!')
                return
            executor_data['video_settings']['fps'] = str(value)
            await message.reply(f'✓ FPS set to {value}')
        
        elif param_name == 'sample_rate':
            value = int(user_input)
            if value not in [8000, 11025, 16000, 22050, 44100, 48000, 88200, 96000]:
                await message.reply('❌ Invalid sample rate! Common: 44100, 48000')
                return
            executor_data['audio_settings']['sample_rate'] = str(value)
            await message.reply(f'✓ Sample rate set to {value}')
        
        elif param_name == 'resolution_custom':
            # Validate resolution format (e.g., 1920x1080)
            if 'x' not in user_input:
                await message.reply('❌ Resolution must be in format: 1920x1080')
                return
            executor_data['video_settings']['resolution'] = user_input
            await message.reply(f'✓ Resolution set to {user_input}')
        
        elif param_name == 'custom':
            # Custom FFmpeg command
            if param_type == 'video':
                executor_data['video_settings']['custom_cmd'] = user_input
            elif param_type == 'audio':
                executor_data['audio_settings']['custom_cmd'] = user_input
            await message.reply(f'✓ Custom FFmpeg command saved:\n<code>{user_input}</code>')
        
        else:
            # Generic text input
            if param_type == 'video':
                executor_data['video_settings'][param_name] = user_input
            elif param_type == 'audio':
                executor_data['audio_settings'][param_name] = user_input
            await message.reply(f'✓ {param_name.title()} set to {user_input}')
        
        # Return to configuration stage
        executor_data['stage'] = 'configure'
        executor_data['waiting_for'] = None
        
        # Update the UI (you'll need to call convert_select again)
        # This depends on your implementation
        
    except ValueError:
        await message.reply('❌ Invalid input! Please send a valid number.')
    except Exception as e:
        LOGGER.error(f'Error processing convert input: {e}')
        await message.reply('❌ Error processing input. Please try again.')
