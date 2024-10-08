
from __future__ import unicode_literals
import discord
import os
import asyncio
from discord.ext import commands
from discord import FFmpegPCMAudio
from discord import Intents
from youtube_search import YoutubeSearch
import yt_dlp
import spotifyTest
from collections import namedtuple 
import shutil
import sqlite3
import Music_Database
from dotenv import load_dotenv
load_dotenv()

connection = sqlite3.connect("Data.db")
c = connection.cursor()
columns = [("Artist", "Text"), ("Song Name", "Text"), ("Server", "Text")]
Music_Database.create_table(c, "Songs", columns)

# Create an instance of a bot. Has intents to do everything for now, just to test
bot = commands.Bot(command_prefix='!', intents = Intents.all())

#not sure how to pass in ffmpeg location sooooooo ffmpeg.exe is in the same location for now
#default settings. for yt_dlp
yt_opts = {
    'format': 'bestaudio/best',
     'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
    
}

@bot.event  
async def on_ready():
    songs_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'songs')

    if os.path.exists(songs_path):
        shutil.rmtree(songs_path)
        print("The 'songs' directory has been deleted.")
    else:
        print("The 'songs' directory does not exist.")
    os.makedirs(songs_path)
    print("The 'songs' directory has been created.")


@bot.command(
    help = "input a number between 1 and 10, and it will suggest that number of songs based on the server's taste profile, ex: (!dj 5)"
)
async def dj(ctx, numSongs):
    suggestions = await spotifyTest.suggest(numSongs, ctx.guild.id)
    suggestedSongs = (suggestions)['tracks']
    
    for song in suggestedSongs:
        await ctx.send("Suggesting " + song['name'] + " by " + song['artists'][0]['name'])
        print("Suggesting ", song['name'], song['artists'][0]['name'])
    print(suggestedSongs)
    playQueue = [play(ctx, song['name'], song['artists'][0]['name']) for song in suggestedSongs]
    await asyncio.gather(*playQueue)



@bot.command(
       help = "Plays from spotify. Search by song name and artist, separated by a comma" 
)
async def playSpotify(ctx, *, search:str):
    # Check if the user is in a voice channel

    searchSplit = search.split(",")

    songName = searchSplit[0]
    songName = songName.strip()
    artistName = ""
    if(len(searchSplit) > 1):
        artistName = searchSplit[1]
        artistName = artistName.strip()
    
    #change to an array of multiple songs, let the user pick
    spotipySongs = await getSongsSpotify(artistName, songName)
    songOptions = []
    if(len(spotipySongs) == 0):
        await ctx.send("no results")
        return
    for song in spotipySongs:
        print(song)
        #trackID = song['']
        #artistID = song['']
        name = song['name']
        artist = song['artists'][0]['name']
        nameAuthor = (name[:70] + '..') if len(name) > 70 else name
        nameAuthor += "-"
        nameAuthor += (artist[:20] + '..') if len(artist) > 20 else artist
        songOptions.append(nameAuthor)


    embed = discord.Embed(title="Which song is it?", description="Chooose")
    select = discord.ui.Select(
        placeholder="Select a song"
    )
    count = 0
    for song in songOptions:
        
        count += 1
        select.add_option(
            label = str(count) + ". " + song
        )
    
    async def callback(interaction): # the function called when the user is done selecting options
            await interaction.response.send_message(f"Queuing {(select.values[0])[3:]}!")
            songChoiceIndex = int(select.values[0][0]) - 1
            songChoice = spotipySongs[songChoiceIndex]
            await play(ctx, songChoice['name'], songChoice['artists'][0]['name'], songChoice['id'], songChoice['artists'][0]['id'])
            
            #could add to database here. would be helpful, while I still have the spotipy stuff
    
    select.callback = callback
    view = discord.ui.View()
    view.add_item(select)

    
    await ctx.send("Choose a song!", view = view, embed = embed)


@bot.command(
       help = "Stops playing the current song and clears the queue" 
)
async def stop(ctx):
    if (ctx.voice_client):
        await ctx.guild.voice_client.disconnect() 
        await ctx.send('Leaving voice channel, clearing Queue')
    else: 
        await ctx.send("Not in a voice channel")
    for i in range(len(queues[ctx.guild.id])):
        await remove(ctx, 0)

queues = {}


SongFile = namedtuple('SongFile', ['fileName', 'name', 'artist', 'trackID', 'artistID'])
#currently no artist, will fill in when spotipy works good
async def addToQueue(song: SongFile, guild):
    if(not guild.id in queues):
        queues[guild.id] = []
    queues[guild.id].append(song)


@bot.command(
        help = "Remove the i-th song from the queue."
)
async def remove(ctx, queueN):
    queueNumber = int(queueN)
    serverQueue = queues[ctx.guild.id]

    await deleteSong(serverQueue[queueNumber])
    serverQueue.pop(queueNumber)

async def deleteSong(song: SongFile):
    os.remove(song.fileName)



@bot.command(
        help = "Searches youtube directly."
)
async def playYT(ctx, *, search):
    await   play(ctx, search, "")
    
#if trackID isn't inputted, it won't get added to the database
async def play(ctx, name, author, trackID = "", artistID = ""):
    # Check if the user is in a voice channel
    if ctx.author.voice is None:
        await ctx.send("You need to be in a voice channel to use this command.")
        return
    else:
        await ctx.send("Now playing " + name + " by " + author)
    
    #serarch for song on spotify, gets full name with artist + song name
    #I'll use this for now, Spotify search thing is really really bad im not sure why
    fullName = name + ', ' + author
    
    #searches on youtube with the full name, and downloads it
    link, fileName = await download(fullName) 
    
    addSong = SongFile(fileName, name, author, trackID, artistID)

    await addToQueue(addSong, ctx.guild)
    
    if(len(queues[ctx.guild.id]) > 1):
        return
    # Get the voice channel of the user
    voice_channel = ctx.author.voice.channel
    
    while(len(queues[ctx.guild.id]) > 0):
        skips[ctx.guild.id] = False
        print("trying my best to play", len(queues[ctx.guild.id]))
        try:
            # Connect to the voice channel
            nextSong = queues[ctx.guild.id][0]
            
            #at this point, I'd probably make a call to add this song to the database
            if(nextSong.artistID != ""):
                Music_Database.insert_row(c, "Songs", (nextSong.artistID, nextSong.trackID, str(ctx.guild.id))) #appends the song, artist and server origin to the database
            print("The song is:", nextSong.artist, nextSong.name)
            connection.commit()
            voice_client = await voice_channel.connect()

            # Play the audio file. Had to set executable to the path, wasn't recognizign for some reason. Weird
            audio_source = FFmpegPCMAudio(executable = 'ffmpeg',source = nextSong.fileName)
            voice_client.play(audio_source)

            # Wait for the audio to finish playing or everyone else to leave, check every 1 second
            while voice_client.is_playing() and len(voice_channel.members) > 1 and not skips[ctx.guild.id]:
                await asyncio.sleep(1)
            print("done")
            # Disconnect from the voice channel after the audio finishes playing. 
            await voice_client.disconnect()
            
        except Exception as e:
            print(e)
            await ctx.send("An error occurred while playing the audio.")
        
        await remove(ctx, 0)

    

skips = {}
@bot.command(
        help = "Skip current song"
)
async def skip(ctx):
    await ctx.send("Skipping")
    skips[ctx.guild.id] = True

@bot.command(
        help = "Shows the songs in the queue"
)
async def queue(ctx):
    
    serverQueue = queues[ctx.guild.id]
    if(len(serverQueue) == 0):
        await ctx.send("The queue is empty!")
        return
    listMsg = "```"
    listMsg += "---------Now Playing----------- \n"
    listMsg += serverQueue[0].name + " - " + serverQueue[0].artist + "\n"
    listMsg += "-------------------------------\n"
    for i in range(1, min(20, len(serverQueue))):
        listMsg += str(i) + ". " + serverQueue[i].name + " - " + serverQueue[i].artist
        listMsg += "\n"
    listMsg += "```"    
    await ctx.send(listMsg)
        


import unicodedata
import re

def slugify(value, allow_unicode = False):
    """
    Taken from https://stackoverflow.com/questions/295135/turn-a-string-into-a-valid-filename
    which was 
    Taken from https://github.com/django/django/blob/master/django/utils/text.py
    Convert to ASCII if 'allow_unicode' is False. Convert spaces or repeated
    dashes to single dashes. Remove characters that aren't alphanumerics,
    underscores, or hyphens. Convert to lowercase. Also strip leading and
    trailing whitespace, dashes, and underscores.
    """
    value = str(value)
    if allow_unicode:
        value = unicodedata.normalize('NFKC', value)
    else:
        value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    value = re.sub(r'[^\w\s-]', '', value.lower())
    return re.sub(r'[-\s]+', '-', value).strip('-_')


#shouldn't be called by the user, it's just a bot command for me to test
@bot.command(help = "Test command")
async def download(songName="creep by radiohead"):
    
    song = await get_first_result(songName)
    fileName = 'songs/' + slugify(song['title'])

    link = 'https://www.youtube.com' + song['url_suffix']
    
    try:
        yt_opts['outtmpl'] = fileName
        with yt_dlp.YoutubeDL(yt_opts) as ydl:
            ydl.download([link])
    except Exception as e:
        print(e)
    return link, fileName + '.mp3'

async def get_first_result(search):
    results = YoutubeSearch(search, max_results=1).to_dict()

    print(results[0])
    return results[0]


async def getSongsSpotify(artist, song):
    result = spotifyTest.search(artist, song)
    print(result)
    return result['tracks']['items']

@bot.command(
        help = "Erases the server's song history in the bot's database. ONLY DO THIS IF YOU'RE READY FOR A CLEAN WIPE"
)
async def clearHistory(ctx):
    #print(ctx.guild.id)
    await spotifyTest.clearHistory(ctx.guild.id)
    await ctx.send("Server history was succesfully cleared!")
    print("test")

#command to end playback

# Would probably want to hide token later, but should work fine for testing
bot.run(os.getenv("DISCORD_TOKEN"))