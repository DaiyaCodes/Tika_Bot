import discord
from discord.ext import commands
import aiohttp
import asyncio
import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import re
import unicodedata

class AnimeNameGame(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data_file = Path('data/anime_game.json')
        self.game_channels: Dict[int, dict] = {}  # guild_id -> game_data
        self.used_names: Dict[int, set] = {}  # guild_id -> set of used names
        self.user_scores: Dict[int, Dict[int, int]] = {}  # guild_id -> {user_id: xp}
        self.last_messages: Dict[int, dict] = {}  # guild_id -> {user_id, name, timestamp, last_letter}
        
        # Ensure data directory exists
        Path('data').mkdir(exist_ok=True)
        self.load_data()
        
    def cog_unload(self):
        """Save data when cog is unloaded"""
        self.save_data()

    def load_data(self):
        """Load game data from file"""
        if self.data_file.exists():
            try:
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                # Convert string keys back to integers for guild/user IDs
                self.game_channels = {int(k): v for k, v in data.get('game_channels', {}).items()}
                self.used_names = {int(k): set(v) for k, v in data.get('used_names', {}).items()}
                self.user_scores = {
                    int(guild_id): {int(user_id): score for user_id, score in users.items()}
                    for guild_id, users in data.get('user_scores', {}).items()
                }
                self.last_messages = {int(k): v for k, v in data.get('last_messages', {}).items()}
                
            except Exception as e:
                self.bot.logger.error(f"Error loading anime game data: {e}")

    def save_data(self):
        """Save game data to file"""
        try:
            data = {
                'game_channels': {str(k): v for k, v in self.game_channels.items()},
                'used_names': {str(k): list(v) for k, v in self.used_names.items()},
                'user_scores': {
                    str(guild_id): {str(user_id): score for user_id, score in users.items()}
                    for guild_id, users in self.user_scores.items()
                },
                'last_messages': {str(k): v for k, v in self.last_messages.items()}
            }
            
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            self.bot.logger.error(f"Error saving anime game data: {e}")

    def normalize_name(self, name: str) -> str:
        """Normalize character name for comparison"""
        # Remove extra spaces and convert to lowercase
        name = ' '.join(name.strip().split()).lower()
        
        # Remove common prefixes/suffixes and normalize
        name = unicodedata.normalize('NFKD', name)
        
        return name

    def get_last_letter(self, name: str) -> str:
        """Get the last meaningful letter from a name"""
        # Remove spaces and punctuation, get last alphabetic character
        clean_name = re.sub(r'[^\w]', '', name.lower())
        
        for char in reversed(clean_name):
            if char.isalpha():
                return char
        
        return clean_name[-1] if clean_name else ''

    def get_first_letter(self, name: str) -> str:
        """Get the first meaningful letter from a name"""
        # Remove spaces and punctuation, get first alphabetic character
        clean_name = re.sub(r'[^\w]', '', name.lower())
        
        for char in clean_name:
            if char.isalpha():
                return char
        
        return clean_name[0] if clean_name else ''

    async def search_anilist_character(self, name: str) -> Optional[dict]:
        """Search for character on AniList API"""
        query = '''
        query ($search: String) {
            Character(search: $search) {
                id
                name {
                    full
                    native
                    alternative
                }
                media {
                    nodes {
                        title {
                            romaji
                            english
                        }
                    }
                }
            }
        }
        '''
        
        variables = {'search': name}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    'https://graphql.anilist.co',
                    json={'query': query, 'variables': variables},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get('data', {}).get('Character')
                    else:
                        return None
        except Exception as e:
            self.bot.logger.error(f"AniList API error: {e}")
            return None

    def calculate_xp(self, time_taken: float) -> int:
        """Calculate XP based on response time"""
        if time_taken <= 20:
            return 2000
        elif time_taken <= 30:
            return 1500
        elif time_taken <= 60:  # 1 minute
            return 800
        elif time_taken <= 21600:  # 6 hours
            return 200
        elif time_taken <= 43200:  # 12 hours
            return 100
        else:  # 1 day and over
            return 20

    @commands.group(name='animegame', aliases=['ag'], invoke_without_command=True)
    async def anime_game(self, ctx):
        """Anime Name Game commands"""
        embed = discord.Embed(
            title="🎌 Anime Name Game",
            description="Play the anime character name game!",
            color=0x00ff00
        )
        embed.add_field(
            name="How to Play",
            value="• Send anime character names in the game channel\n"
                  "• Next name must start with the last letter of previous name\n"
                  "• Each name can only be used once\n"
                  "• Faster responses = more XP!",
            inline=False
        )
        embed.add_field(
            name="Commands",
            value="`/animegame setchannel` - Set game channel\n"
                  "`/animegame leaderboard` - View XP leaderboard\n"
                  "`/animegame reset` - Reset game (Admin only)\n"
                  "`/animegame stats` - View your stats",
            inline=False
        )
        await ctx.send(embed=embed)

    @anime_game.command(name='setchannel')
    @commands.has_permissions(manage_channels=True)
    async def set_channel(self, ctx, channel: discord.TextChannel = None):
        """Set the anime name game channel"""
        if channel is None:
            channel = ctx.channel
        
        guild_id = ctx.guild.id
        
        # Initialize guild data if not exists
        if guild_id not in self.game_channels:
            self.game_channels[guild_id] = {}
            self.used_names[guild_id] = set()
            self.user_scores[guild_id] = {}
            self.last_messages[guild_id] = {}
        
        self.game_channels[guild_id]['channel_id'] = channel.id
        self.save_data()
        
        embed = discord.Embed(
            title="✅ Game Channel Set",
            description=f"Anime name game is now active in {channel.mention}!",
            color=0x00ff00
        )
        embed.add_field(
            name="Rules",
            value="• Only anime character names allowed\n"
                  "• Next name starts with last letter of previous name\n"
                  "• No repeated names\n"
                  "• Verified through AniList database",
            inline=False
        )
        await ctx.send(embed=embed)

    @anime_game.command(name='leaderboard', aliases=['lb', 'top'])
    async def leaderboard(self, ctx, page: int = 1):
        """Show XP leaderboard"""
        guild_id = ctx.guild.id
        
        if guild_id not in self.user_scores or not self.user_scores[guild_id]:
            await ctx.send("📊 No scores recorded yet! Start playing to see the leaderboard.")
            return
        
        # Sort users by XP
        sorted_users = sorted(
            self.user_scores[guild_id].items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        # Pagination
        per_page = 10
        total_pages = (len(sorted_users) + per_page - 1) // per_page
        page = max(1, min(page, total_pages))
        
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        page_users = sorted_users[start_idx:end_idx]
        
        embed = discord.Embed(
            title="🏆 Anime Name Game Leaderboard",
            color=0xffd700
        )
        
        leaderboard_text = ""
        for i, (user_id, xp) in enumerate(page_users, start=start_idx + 1):
            user = self.bot.get_user(user_id)
            username = user.display_name if user else f"Unknown User ({user_id})"
            
            # Add medal emojis for top 3
            medal = ""
            if i == 1:
                medal = "🥇 "
            elif i == 2:
                medal = "🥈 "
            elif i == 3:
                medal = "🥉 "
            
            leaderboard_text += f"{medal}**{i}.** {username} - {xp:,} XP\n"
        
        embed.description = leaderboard_text
        embed.set_footer(text=f"Page {page}/{total_pages} • Total Players: {len(sorted_users)}")
        
        await ctx.send(embed=embed)

    @anime_game.command(name='stats')
    async def stats(self, ctx, user: discord.Member = None):
        """Show user stats"""
        if user is None:
            user = ctx.author
        
        guild_id = ctx.guild.id
        user_id = user.id
        
        if guild_id not in self.user_scores or user_id not in self.user_scores[guild_id]:
            await ctx.send(f"📊 {user.display_name} hasn't played the anime name game yet!")
            return
        
        xp = self.user_scores[guild_id][user_id]
        
        # Find user's rank
        sorted_users = sorted(
            self.user_scores[guild_id].items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        rank = next((i + 1 for i, (uid, _) in enumerate(sorted_users) if uid == user_id), 0)
        
        embed = discord.Embed(
            title=f"📊 {user.display_name}'s Stats",
            color=0x00ff00
        )
        embed.add_field(name="XP", value=f"{xp:,}", inline=True)
        embed.add_field(name="Rank", value=f"#{rank}", inline=True)
        embed.add_field(name="Total Players", value=f"{len(sorted_users)}", inline=True)
        
        embed.set_thumbnail(url=user.display_avatar.url)
        await ctx.send(embed=embed)

    @anime_game.command(name='reset')
    @commands.has_permissions(administrator=True)
    async def reset_game(self, ctx):
        """Reset the anime name game (Admin only)"""
        guild_id = ctx.guild.id
        
        # Confirmation
        embed = discord.Embed(
            title="⚠️ Reset Confirmation",
            description="This will reset all game data including:\n"
                       "• All used names\n"
                       "• All player XP and scores\n"
                       "• Game progress\n\n"
                       "This action cannot be undone!",
            color=0xff0000
        )
        
        view = ConfirmView()
        message = await ctx.send(embed=embed, view=view)
        
        await view.wait()
        
        if view.confirmed:
            # Reset all data for this guild
            if guild_id in self.used_names:
                self.used_names[guild_id].clear()
            if guild_id in self.user_scores:
                self.user_scores[guild_id].clear()
            if guild_id in self.last_messages:
                self.last_messages[guild_id].clear()
            
            self.save_data()
            
            embed = discord.Embed(
                title="✅ Game Reset",
                description="Anime name game has been reset successfully!",
                color=0x00ff00
            )
            await message.edit(embed=embed, view=None)
        else:
            embed = discord.Embed(
                title="❌ Reset Cancelled",
                description="Game reset has been cancelled.",
                color=0xff0000
            )
            await message.edit(embed=embed, view=None)

    @commands.Cog.listener()
    async def on_message(self, message):
        """Handle messages in game channels"""
        if message.author.bot:
            return
        
        guild_id = message.guild.id
        channel_id = message.channel.id
        
        # Check if this is a game channel
        if (guild_id not in self.game_channels or 
            self.game_channels[guild_id].get('channel_id') != channel_id):
            return
        
        # Initialize guild data if needed
        if guild_id not in self.used_names:
            self.used_names[guild_id] = set()
        if guild_id not in self.user_scores:
            self.user_scores[guild_id] = {}
        if guild_id not in self.last_messages:
            self.last_messages[guild_id] = {}
        
        character_name = message.content.strip()
        
        # Skip if empty or command
        if not character_name or character_name.startswith(('/', '!!')):
            return
        
        # Check if name was already used
        normalized_name = self.normalize_name(character_name)
        if normalized_name in self.used_names[guild_id]:
            # Find who used it first
            embed = discord.Embed(
                title="❌ Name Already Used",
                description=f"The name **{character_name}** has already been used!",
                color=0xff0000
            )
            await message.reply(embed=embed, delete_after=10)
            await message.delete(delay=2)
            return
        
        # Check if follows the letter rule
        last_msg = self.last_messages[guild_id]
        if last_msg and 'last_letter' in last_msg:
            required_letter = last_msg['last_letter']
            first_letter = self.get_first_letter(character_name)
            
            if first_letter != required_letter:
                embed = discord.Embed(
                    title="❌ Wrong Starting Letter",
                    description=f"The name must start with **{required_letter.upper()}**\n"
                               f"Your name starts with **{first_letter.upper()}**",
                    color=0xff0000
                )
                await message.reply(embed=embed, delete_after=10)
                await message.delete(delay=2)
                return
        
        # Verify character exists on AniList
        async with message.channel.typing():
            character_data = await self.search_anilist_character(character_name)
        
        if not character_data:
            embed = discord.Embed(
                title="❌ Character Not Found",
                description=f"**{character_name}** was not found in the AniList database.\n"
                           "Please use a valid anime character name.",
                color=0xff0000
            )
            await message.reply(embed=embed, delete_after=15)
            await message.delete(delay=2)
            return
        
        # Calculate XP based on response time
        current_time = time.time()
        if last_msg and 'timestamp' in last_msg:
            time_taken = current_time - last_msg['timestamp']
            xp_gained = self.calculate_xp(time_taken)
        else:
            xp_gained = 2000  # First message gets full XP
            time_taken = 0
        
        # Add to used names and update scores
        self.used_names[guild_id].add(normalized_name)
        
        user_id = message.author.id
        if user_id not in self.user_scores[guild_id]:
            self.user_scores[guild_id][user_id] = 0
        self.user_scores[guild_id][user_id] += xp_gained
        
        # Update last message info
        last_letter = self.get_last_letter(character_name)
        self.last_messages[guild_id] = {
            'user_id': user_id,
            'name': character_name,
            'timestamp': current_time,
            'last_letter': last_letter
        }
        
        # Save data
        self.save_data()
        
        # Create success embed
        embed = discord.Embed(
            title="✅ Valid Character!",
            description=f"**{character_name}** by {message.author.mention}",
            color=0x00ff00
        )
        
        # Add character info
        char_name = character_data.get('name', {})
        full_name = char_name.get('full', character_name)
        if char_name.get('native'):
            embed.add_field(name="Native Name", value=char_name['native'], inline=True)
        
        # Add anime info
        media = character_data.get('media', {}).get('nodes', [])
        if media:
            anime_title = media[0].get('title', {}).get('romaji', 'Unknown')
            embed.add_field(name="From Anime", value=anime_title, inline=True)
        
        embed.add_field(name="XP Gained", value=f"+{xp_gained:,} XP", inline=True)
        
        if time_taken > 0:
            if time_taken < 60:
                time_str = f"{time_taken:.1f}s"
            elif time_taken < 3600:
                time_str = f"{time_taken/60:.1f}m"
            else:
                time_str = f"{time_taken/3600:.1f}h"
            embed.add_field(name="Response Time", value=time_str, inline=True)
        
        embed.add_field(
            name="Next Letter",
            value=f"Next name must start with **{last_letter.upper()}**",
            inline=False
        )
        
        embed.set_footer(text=f"Total XP: {self.user_scores[guild_id][user_id]:,}")
        
        await message.reply(embed=embed)

class ConfirmView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=30)
        self.confirmed = False

    @discord.ui.button(label='Confirm Reset', style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = True
        self.stop()

    @discord.ui.button(label='Cancel', style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = False
        self.stop()

async def setup(bot):
    await bot.add_cog(AnimeNameGame(bot))