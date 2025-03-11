import os
import json
import logging
import discord
import asyncio

from discord.ext import commands
from datetime import datetime, timedelta

# Configuración de logging
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] [%(levelname)-8s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')


TOKEN = os.getenv('TOKEN')

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

reservas = {}  # Diccionario de reservas
usuarios_con_turno = {}  # Controla qué usuarios tienen un turno


def guardar_reservas():
    """ Guarda las reservas en un archivo JSON. """
    with open("reservas.json", "w") as f:
        json.dump({k: (v[0].id, v[1].strftime("%Y-%m-%d %H:%M")) for k, v in reservas.items()}, f)


def cargar_reservas():
    """ Carga las reservas desde un archivo JSON al iniciar el bot. """
    global reservas, usuarios_con_turno

    try:
        with open("reservas.json", "r") as f:
            data = json.load(f)
            reservas = {k: (bot.get_user(v[0]), datetime.strptime(v[1], "%Y-%m-%d %H:%M")) for k, v in data.items()}
            usuarios_con_turno = {v[0]: datetime.strptime(v[1], "%Y-%m-%d %H:%M") for k, v in data.items()}
    except (FileNotFoundError, json.JSONDecodeError):
        reservas = {}
        usuarios_con_turno = {}


async def programar_aviso(channel, fecha_hora, usuario):
    """ Programa un aviso 5 minutos antes del turno. """
    ahora = datetime.now()
    tiempo_espera = (fecha_hora - ahora).total_seconds() - (5 * 60)

    if tiempo_espera > 0:
        await asyncio.sleep(tiempo_espera)
        await channel.send(f"⏳ {usuario.mention}, tu turno comienza en 5 minutos.")

    await asyncio.sleep(5 * 60)

    if fecha_hora.strftime("%Y-%m-%d %H:%M") in reservas:
        reservas.pop(fecha_hora.strftime("%Y-%m-%d %H:%M"))
        usuarios_con_turno.pop(usuario, None)
        guardar_reservas()
        await channel.send(f"⏳ {usuario.mention}, tu turno ha comenzado.")


@bot.event
async def on_ready():
    logging.info("Bot online")
    cargar_reservas()


@bot.event
async def on_message(message):
    if bot.user in message.mentions:
        contenido = message.content.replace(f"<@{bot.user.id}>", "").strip()
        logging.info(f"Comando recibido: {contenido}")

    await bot.process_commands(message)


@bot.command()
async def reservar(message, fecha_hora_str: str):
    """ Permite reservar un turno en formato DIA/HH:MM """
    global reservas, usuarios_con_turno

    try:
        hoy = datetime.now()
        dia, hora = fecha_hora_str.split("/")  # Separar el día y la hora
        fecha_hora = datetime.strptime(f"{hoy.year}-{hoy.month}-{dia} {hora}", "%Y-%m-%d %H:%M")

        if fecha_hora < hoy:
            respuesta = f"{message.author.mention}, no puedes reservar en el pasado."
            logging.warning(f"[reserva] - [{message.author.mention}] fecha introducida {fecha_hora} incorrecta")
            await message.channel.send(respuesta)
            return

        if message.author in usuarios_con_turno:
            respuesta = f"{message.author.mention}, ya tienes una reserva para el {usuarios_con_turno[message.author].strftime('%d/%H:%M')}."
            logging.warning(f"[reserva] - [{message.author.mention}] ya tiene una reserva activa")
            await message.channel.send(respuesta)
            return

        clave_reserva = fecha_hora.strftime("%Y-%m-%d %H:%M")

        if clave_reserva in reservas:
            respuesta = f"{message.author.mention}, ya hay una reserva a las {hora} el día {dia}. Intenta con otra hora."
            logging.warning(f"[reserva] - [{message.author.mention}] ya hay una reserva en fecha introducida")
            await message.channel.send(respuesta)

        else:
            reservas[clave_reserva] = (message.author, fecha_hora + timedelta(hours=1))
            usuarios_con_turno[message.author] = fecha_hora
            respuesta = f"✅ {message.author.mention}, tu reserva ha sido confirmada para el día {dia} a las {hora}."
            logging.info(f"[reserva] - [{message.author.mention}] reserva confirmada {fecha_hora}")

            guardar_reservas()

            await message.channel.send(respuesta)
            await programar_aviso(message.channel, fecha_hora, message.author)

    except ValueError:
        respuesta = f"{message.author.mention}, el formato es incorrecto. Usa: `@{bot.user.name} reservar DD/HH:MM`."
        logging.error(f"[reserva] - [{message.author.mention}] formato introducido incorrecto")
        await message.channel.send(respuesta)


@bot.command()
async def liberar(message):
    global reservas, usuarios_con_turno

    if message.author in usuarios_con_turno:
        fecha_reserva = usuarios_con_turno.pop(message.author).strftime("%Y-%m-%d %H:%M")
        reservas.pop(fecha_reserva, None)
        guardar_reservas()
        respuesta = f"✅ {message.author.mention}, tu turno para el {fecha_reserva} ha sido liberado."
    else:
        respuesta = f"{message.author.mention}, no tienes ninguna reserva activa para liberar."

    logging.info(f"[liberar] - [{message.author.mention}] {respuesta}")
    await message.channel.send(respuesta)


@bot.command()
async def turnos(message):
    if reservas:
        mensaje = "📅 **Reservas programadas:**\n"
        for clave, (usuario, fin_turno) in sorted(reservas.items()):
            mensaje += f"🔹 {usuario.mention} - {clave} → hasta {fin_turno.strftime('%H:%M')}\n"

    else:
        mensaje = "📭 No hay reservas activas."

    logging.info(f"[turnos] - [{message.author.mention}] Solicita lista de turnos")
    await message.channel.send(mensaje)


@bot.command()
async def ayuda(message):
    """ Muestra los comandos disponibles y su uso. """
    mensaje = (
        "**📖 Comandos del bot de turnos:**\n"
        "🔹 !reservar DD/HH:MM - Reserva un turno en una fecha y hora específica.\n"
        "🔹 !turnos - Muestra la lista de reservas programadas.\n"
        "🔹 !liberar - Libera tu turno si ya no lo necesitas.\n"
        "🔹 !ayuda - Muestra esta ayuda.\n\n"
        "**📜 Reglas del sistema de turnos:**\n"
        "✅ Solo puedes tener **una reserva activa** a la vez.\n"
        "✅ Cada turno dura **1 hora automáticamente**.\n"
        "✅ Cuando un turno finaliza, se **libera automáticamente**.\n"
        "📌 *Ejemplo:* !reservar 2025-03-12 15:00"
    )

    logging.info(f"[ayuda] - [{message.author.mention}] Solicita ayuda")
    await message.channel.send(mensaje)


bot.run(TOKEN)
