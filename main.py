import discord
from discord.ext import commands
import logging
import os
import asyncio
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)

class OptimizedBot(commands.Bot):
    def __init__(self):
        # Bot configuration with optimized intents
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.guilds = True
        
        super().__init__(
            command_prefix=['/', '!!'],
            intents=intents,
            help_command=None,  # Disable default help command
            case_insensitive=True,
            strip_after_prefix=True
        )
        
        self.logger = logging.getLogger(__name__)
        self.startup_extensions = [
            'cogs.fun_commands',
            'cogs.moderation', 
            'cogs.word_blocker',
            'cogs.custom_roles'
        ]

    async def setup_hook(self):
        """Called when the bot is starting up"""
        self.logger.info("Setting up bot...")
        
        # Ensure data directory exists
        Path('data').mkdir(exist_ok=True)
        
        # Load all cogs
        await self.load_cogs()
        
        # Sync slash commands
        try:
            synced = await self.tree.sync()
            self.logger.info(f"Synced {len(synced)} slash command(s)")
        except Exception as e:
            self.logger.error(f"Failed to sync commands: {e}")

    async def load_cogs(self):
        """Load all cogs with error handling"""
        for extension in self.startup_extensions:
            try:
                await self.load_extension(extension)
                self.logger.info(f"Loaded {extension}")
            except Exception as e:
                self.logger.error(f"Failed to load {extension}: {e}")

    async def on_ready(self):
        """Called when bot is ready"""
        self.logger.info(f'{self.user} has connected to Discord!')
        self.logger.info(f'Bot is in {len(self.guilds)} guilds')
        
        # Set bot status
        activity = discord.Game(name="with custom roles and fun commands!")
        await self.change_presence(status=discord.Status.online, activity=activity)

    async def on_message(self, message):
        """Process messages with word blocking"""
        if message.author.bot:
            return
        
        # Process word blocking before other commands
        word_blocker = self.get_cog('WordBlocker')
        if word_blocker:
            blocked = await word_blocker.check_blocked_words(message)
            if blocked:
                return  # Message was deleted, don't process further
        
        await self.process_commands(message)

    async def on_command_error(self, ctx, error):
        """Global error handler"""
        if isinstance(error, commands.CommandNotFound):
            return  # Ignore unknown commands
        
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ You don't have permission to use this command!", delete_after=5)
            return
        
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"⏰ Command on cooldown. Try again in {error.retry_after:.2f}s", delete_after=5)
            return
        
        self.logger.error(f"Command error in {ctx.command}: {error}")
        await ctx.send("❌ An unexpected error occurred!", delete_after=5)

    async def close(self):
        """Cleanup when bot is shutting down"""
        self.logger.info("Shutting down bot...")
        await super().close()

async def main():
    """Main function to run the bot"""
    bot = OptimizedBot()
    
    # Get token from environment variable or file
    token = os.getenv('BOT_TOKEN')
    if not token:
        try:
            with open('token.txt', 'r') as f:
                token = f.read().strip()
        except FileNotFoundError:
            logging.error("No bot token found! Set BOT_TOKEN environment variable or create token.txt")
            return
    
    try:
        await bot.start(token)
    except KeyboardInterrupt:
        logging.info("Bot stopped by user")
    except Exception as e:
        logging.error(f"Bot crashed: {e}")
    finally:
        await bot.close()

if __name__ == '__main__':
    asyncio.run(main())