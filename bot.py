import os
import logging
import asyncio
import json
import redis
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import openai
import random

# ==================== CONFIGURATION ====================
# Yahan apne environment variables set karo
GROUP_BOT_TOKEN = "8335185001:AAF1RyE02jJTiV66mE_uwH-_plO8iHNaKPo"  # @BotFather se group bot ka token
PERSONAL_BOT_TOKEN = "8477849714:AAEhJpSYBqE9gJPbMm9sFTdQBiT3dJK_uHA"  # @BotFather se personal bot ka token
OPENAI_API_KEY = "71c54b3194d2ae6d93216b13da9ed72b"  # platform.openai.com se API key
REQUIRED_CHANNEL = "@NRX_EMPIRE"  # Force join channel

# Redis configuration (Railway automatically provides)
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379')

# Rate limiting
MAX_REQUESTS_PER_MINUTE = 30

# ==================== LOGGING SETUP ====================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ==================== REDIS STORAGE ====================
class RedisStorage:
    def __init__(self):
        try:
            self.redis_client = redis.from_url(REDIS_URL, decode_responses=True)
            self.redis_client.ping()
            logger.info("✅ Redis connected successfully")
        except Exception as e:
            logger.warning(f"❌ Redis not available, using in-memory storage: {e}")
            self.redis_client = None
            self.memory_storage = {}
    
    def get_conversation(self, user_id):
        try:
            if self.redis_client:
                data = self.redis_client.get(f"conversation:{user_id}")
                return json.loads(data) if data else None
            else:
                return self.memory_storage.get(f"conversation:{user_id}")
        except Exception as e:
            logger.error(f"Storage get error: {e}")
            return None
    
    def set_conversation(self, user_id, conversation):
        try:
            if self.redis_client:
                self.redis_client.setex(
                    f"conversation:{user_id}", 
                    3600,  # 1 hour expiry
                    json.dumps(conversation)
                )
            else:
                self.memory_storage[f"conversation:{user_id}"] = conversation
        except Exception as e:
            logger.error(f"Storage set error: {e}")
    
    def delete_conversation(self, user_id):
        try:
            if self.redis_client:
                self.redis_client.delete(f"conversation:{user_id}")
            else:
                self.memory_storage.pop(f"conversation:{user_id}", None)
        except Exception as e:
            logger.error(f"Storage delete error: {e}")
    
    def is_rate_limited(self, user_id):
        try:
            if self.redis_client:
                key = f"rate_limit:{user_id}"
                current = self.redis_client.get(key)
                if current and int(current) >= MAX_REQUESTS_PER_MINUTE:
                    return True
                return False
            else:
                # Simple in-memory rate limiting
                key = f"rate_limit:{user_id}"
                current = self.memory_storage.get(key, 0)
                return current >= MAX_REQUESTS_PER_MINUTE
        except Exception as e:
            logger.error(f"Rate limit check error: {e}")
            return False
    
    def increment_rate_limit(self, user_id):
        try:
            if self.redis_client:
                key = f"rate_limit:{user_id}"
                pipeline = self.redis_client.pipeline()
                pipeline.incr(key)
                pipeline.expire(key, 60)  # 1 minute
                pipeline.execute()
            else:
                key = f"rate_limit:{user_id}"
                current = self.memory_storage.get(key, 0)
                self.memory_storage[key] = current + 1
                # Simple cleanup - in production use proper TTL
                if len(self.memory_storage) > 1000:
                    self.memory_storage.clear()
        except Exception as e:
            logger.error(f"Rate limit increment error: {e}")

# ==================== MAIN BOT CLASS ====================
class AllInOneAIBot:
    def __init__(self):
        # Validate tokens
        self.validate_tokens()
        
        # Initialize storage
        self.storage = RedisStorage()
        
        # Initialize both bots
        self.group_app = Application.builder().token(GROUP_BOT_TOKEN).build()
        self.personal_app = Application.builder().token(PERSONAL_BOT_TOKEN).build()
        
        # Configure OpenAI
        openai.api_key = OPENAI_API_KEY
        
        logger.info("🤖 Initializing All-in-One AI Bot...")
        self.setup_handlers()
    
    def validate_tokens(self):
        """Check if all required tokens are set"""
        missing = []
        if GROUP_BOT_TOKEN == "YOUR_GROUP_BOT_TOKEN_HERE":
            missing.append("GROUP_BOT_TOKEN")
        if PERSONAL_BOT_TOKEN == "YOUR_PERSONAL_BOT_TOKEN_HERE":
            missing.append("PERSONAL_BOT_TOKEN") 
        if OPENAI_API_KEY == "YOUR_OPENAI_API_KEY_HERE":
            missing.append("OPENAI_API_KEY")
        
        if missing:
            error_msg = f"❌ Please set these tokens in the code: {', '.join(missing)}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        logger.info("✅ All tokens validated successfully")

    async def check_channel_membership(self, user_id, bot):
        """Check if user is member of required channel"""
        try:
            chat_member = await bot.get_chat_member(REQUIRED_CHANNEL, user_id)
            return chat_member.status in ['member', 'administrator', 'creator']
        except Exception as e:
            logger.error(f"Channel check error: {e}")
            return False

    def setup_handlers(self):
        # ========== GROUP BOT HANDLERS ==========
        
        async def group_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
            welcome_message = """🤖 Welcome to AI Group Bot!

Mai yahan group mein aapki madad karne ke liye hoon. 
Koi bhi message karein, mai reply dunga!

Developer: @JustMrPerfect"""
            await update.message.reply_text(welcome_message)
        
        async def group_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
            help_message = """💫 Group AI Bot Help

Mai group mein naturally engage karta hoon:
• New members ka welcome karta hoon
• Messages ka reply deta hoon  
• Entertainment provide karta hoon

Simply chat normally! 😊"""
            await update.message.reply_text(help_message)
        
        async def welcome_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
            for member in update.message.new_chat_members:
                if not member.is_bot:
                    welcome_msg = f"""🎉 Welcome {member.first_name} to the group!

Mai yahan aapki madad karne ke liye hoon. 
Koi bhi sawal ya baat karne ke liye message karein!"""
                    await update.message.reply_text(welcome_msg)
                    
                    # Auto follow-up after 3 seconds
                    await asyncio.sleep(3)
                    follow_up = f"Hey {member.first_name}! 👋 Koi help chahiye to batao!"
                    await update.message.reply_text(follow_up)
        
        async def handle_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if update.message.from_user.is_bot:
                return
                
            user_id = update.message.from_user.id
            user_name = update.message.from_user.first_name
            message_text = update.message.text
            
            # Rate limiting check
            if self.storage.is_rate_limited(user_id):
                return
                
            self.storage.increment_rate_limit(user_id)
            
            # Get bot username
            bot_username = (await self.group_app.bot.get_me()).username
            
            # Check if bot is mentioned or random response
            is_mentioned = bot_username and f"@{bot_username}" in message_text
            is_reply_to_bot = (update.message.reply_to_message and 
                              update.message.reply_to_message.from_user.username == bot_username)
            should_respond = is_mentioned or is_reply_to_bot or random.random() < 0.4
            
            if should_respond:
                try:
                    await update.message.chat.send_action(action="typing")
                    
                    # Get or create conversation
                    conversation = self.storage.get_conversation(user_id) or [
                        {
                            "role": "system",
                            "content": f"You are a friendly AI assistant in a Telegram group. Be helpful, engaging and fun. User's name is {user_name}. Keep responses short and conversational."
                        }
                    ]
                    
                    # Add user message
                    conversation.append({"role": "user", "content": message_text})
                    
                    # Limit history
                    if len(conversation) > 8:
                        conversation = [conversation[0]] + conversation[-6:]
                    
                    # Get AI response
                    response = await self.get_ai_response(conversation, is_group=True)
                    
                    if response:
                        conversation.append({"role": "assistant", "content": response})
                        self.storage.set_conversation(user_id, conversation)
                        await update.message.reply_text(response, reply_to_message_id=update.message.message_id)
                        
                except Exception as e:
                    logger.error(f"Group message error: {e}")
        
        async def handle_group_non_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
            responses = ["Nice! 👌", "Mast hai! 😄", "Interesting! 🤔", "Accha hai! 👍", "Wah! 🎉"]
            await update.message.reply_text(random.choice(responses), reply_to_message_id=update.message.message_id)
        
        # ========== PERSONAL BOT HANDLERS ==========
        
        async def personal_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user_id = update.effective_user.id
            user_name = update.effective_user.first_name
            
            # Check channel membership
            is_member = await self.check_channel_membership(user_id, self.personal_app.bot)
            
            if not is_member:
                join_message = f"""👋 Hello {user_name}!

📢 Please join our channel first to use this bot:

{REQUIRED_CHANNEL}

Once you've joined, send /start again!"""
                await update.message.reply_text(join_message)
                return
            
            welcome_msg = f"""🎉 Welcome {user_name}!

Mai aapka personal AI assistant hoon. Aap mujhse kuch bhi pooch sakte hain:

• Questions & Answers
• Creative Writing  
• Coding Help
• General Chat
• Aur bhi kuch bhi!

Simply type your message and I'll help you! 😊

Developer: @JustMrPerfect"""
            
            await update.message.reply_text(welcome_msg)
            
            # Initialize conversation
            self.storage.set_conversation(user_id, [
                {
                    "role": "system", 
                    "content": f"You are a helpful, friendly AI assistant in a private Telegram chat. Be conversational and engaging. User's name is {user_name}."
                }
            ])
        
        async def personal_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user_id = update.effective_user.id
            
            is_member = await self.check_channel_membership(user_id, self.personal_app.bot)
            if not is_member:
                await update.message.reply_text(f"📢 Please join {REQUIRED_CHANNEL} first!")
                return
                
            help_msg = """💫 **Personal AI Assistant Help**

Mai yahan hoon aapki har tarah se madad karne ke liye:

• **General Questions** - Koi bhi sawal poochhe
• **Creative Work** - Writing, ideas, content
• **Technical Help** - Coding, technology  
• **Learning** - Explanations, tutorials
• **Entertainment** - Stories, jokes, fun chat

Simply type your message and I'll respond!

Developer: @JustMrPerfect"""
            
            await update.message.reply_text(help_msg)
        
        async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user_id = update.effective_user.id
            self.storage.delete_conversation(user_id)
            await update.message.reply_text('🔄 Conversation cleared! Fresh start!')
        
        async def handle_private_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user_id = update.effective_user.id
            message_text = update.message.text
            
            # Rate limiting
            if self.storage.is_rate_limited(user_id):
                await update.message.reply_text("⚠️ Please wait a moment before sending more messages.")
                return
                
            self.storage.increment_rate_limit(user_id)
            
            # Check membership
            is_member = await self.check_channel_membership(user_id, self.personal_app.bot)
            if not is_member:
                await update.message.reply_text(f"❌ Please join {REQUIRED_CHANNEL} first!")
                return
            
            try:
                await update.message.chat.send_action(action="typing")
                
                # Get conversation
                conversation = self.storage.get_conversation(user_id) or [
                    {
                        "role": "system",
                        "content": "You are a helpful, friendly AI assistant in a private Telegram chat."
                    }
                ]
                
                # Add user message
                conversation.append({"role": "user", "content": message_text})
                
                # Limit history
                if len(conversation) > 12:
                    conversation = [conversation[0]] + conversation[-10:]
                
                # Get AI response
                response = await self.get_ai_response(conversation, is_group=False)
                
                if response:
                    conversation.append({"role": "assistant", "content": response})
                    self.storage.set_conversation(user_id, conversation)
                    
                    # Send response (handle long messages)
                    if len(response) <= 4096:
                        await update.message.reply_text(response)
                    else:
                        for i in range(0, len(response), 4096):
                            await update.message.reply_text(response[i:i+4096])
                            await asyncio.sleep(0.5)
                else:
                    await update.message.reply_text('Sorry, technical issue. Please try again!')
                    
            except Exception as e:
                logger.error(f"Private message error: {e}")
                await update.message.reply_text('Oops! Kuch gadbad ho gayi. Please try again!')
        
        async def handle_private_non_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
            await update.message.reply_text('📝 I currently support text messages only. Send me any text!')
        
        # ========== REGISTER HANDLERS ==========
        
        # Group bot handlers
        self.group_app.add_handler(CommandHandler("start", group_start))
        self.group_app.add_handler(CommandHandler("help", group_help))
        self.group_app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_members))
        self.group_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_group_message))
        self.group_app.add_handler(MessageHandler(~filters.TEXT, handle_group_non_text))
        
        # Personal bot handlers
        self.personal_app.add_handler(CommandHandler("start", personal_start))
        self.personal_app.add_handler(CommandHandler("help", personal_help))
        self.personal_app.add_handler(CommandHandler("clear", clear_command))
        self.personal_app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE & ~filters.COMMAND, handle_private_message))
        self.personal_app.add_handler(MessageHandler(~filters.TEXT & filters.ChatType.PRIVATE, handle_private_non_text))
        
        # Error handlers
        self.group_app.add_error_handler(self.error_handler)
        self.personal_app.add_error_handler(self.error_handler)
        
        logger.info("✅ All bot handlers setup complete")
    
    async def get_ai_response(self, messages, is_group=False):
        try:
            client = openai.OpenAI(api_key=OPENAI_API_KEY)
            
            # Different settings for group vs personal
            if is_group:
                model = "gpt-3.5-turbo"
                max_tokens = 150
            else:
                model = "gpt-3.5-turbo" 
                max_tokens = 500
            
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.7
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            if is_group:
                return "Mai abhi busy hoon, thodi der baad try karein! 😊"
            else:
                return "I'm currently experiencing high traffic. Please try again in a moment! 😊"
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        logger.error(f"Bot error: {context.error}")
    
    async def run_bots(self):
        """Run both bots concurrently"""
        logger.info("🚀 Starting All-in-One AI Bots...")
        logger.info("📱 Group Bot: Ready for groups")
        logger.info("💬 Personal Bot: Ready for DMs (with channel check)")
        
        tasks = [
            self.group_app.run_polling(
                allowed_updates=Update.ALL_TYPES, 
                drop_pending_updates=True,
                close_loop=False
            ),
            self.personal_app.run_polling(
                allowed_updates=Update.ALL_TYPES, 
                drop_pending_updates=True,
                close_loop=False
            )
        ]
        
        # Run both bots
        await asyncio.gather(*tasks, return_exceptions=True)
    
    def run(self):
        """Run bots with asyncio"""
        try:
            # Check if running on Railway
            if os.getenv('RAILWAY_ENVIRONMENT'):
                logger.info("🚄 Running on Railway platform")
            
            asyncio.run(self.run_bots())
        except KeyboardInterrupt:
            logger.info("🛑 Bots stopped by user")
        except Exception as e:
            logger.error(f"❌ Failed to start bots: {e}")
            logger.info("💡 Please check if all tokens are set correctly in the code")

# ==================== RUN THE BOT ====================
if __name__ == "__main__":
    print("=" * 50)
    print("🤖 ALL-IN-ONE TELEGRAM AI BOT")
    print("📝 Single File Solution")
    print("🚀 Starting up...")
    print("=" * 50)
    
    try:
        bot = AllInOneAIBot()
        bot.run()
    except Exception as e:
        print(f"❌ Failed to start: {e}")
        print("\n💡 SETUP INSTRUCTIONS:")
        print("1. GROUP_BOT_TOKEN - @BotFather se group bot banayein")
        print("2. PERSONAL_BOT_TOKEN - @BotFather se personal bot banayein") 
        print("3. OPENAI_API_KEY - platform.openai.com se API key lein")
        print("4. REQUIRED_CHANNEL - Apna channel username daalein")
        print("\n🔧 Code mein line 10-13 par tokens update karein!")
