"""
handel the database events
:copyright: (c) xgreenapple
:license: MIT.
"""

import asyncio
import logging
import sys
import traceback
import asyncpg

from datetime import timedelta, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pepebot import pepebot

_log = logging.getLogger(__name__)


class Events:
    """ base class for asyncio tasks

    arguments
    ~~~~~~~~~
    bot: :class:`pepebot`
        takes the bot parameter
    database: :class:`asyncpg.pool`
        asyncpg pool to execute commands to database
    """

    def __init__(self, bot):
        self.bot: pepebot = bot
        self.current_data = None
        self._tasks: asyncio.Task = self.LoadTasks()
        self._next_data: asyncio.Event = asyncio.Event()
        self.database = self.bot.Database

    async def InitializeTasks(self):
        """ initialize the tasks
        """
        pass
 
    def LoadTasks(self) -> asyncio.Task:
        """
        :return: asyncio.Task
        """
        return self.bot.loop.create_task(self.InitializeTasks())

    def createTask(self):
        self._next_data.set()

    async def CleanUp(self):
        if self._tasks.cancelled():
            self._tasks.cancel()


class CheckEconomyItems(Events):

    def __init__(self, bot):
        super().__init__(
            bot=bot
        )

    async def InitializeTasks(self):
        """task event manager

        initialize the task and sleep until its complete
        run until the bot is closed, if data given is none
        then it will wait for the data to receive
        """
        try:
            while not self.bot.is_closed():
                data = await self.Get_initialize_data()
                # data is null skipping the loop
                if not data:
                    _log.warning("skipping this loop the data is None")
                    continue
                time = data['expired']
                # time is null skipping the loop
                if not time:
                    _log.warning("skipping this event loop timestamp is null")
                    continue
                # get the current time
                now = datetime.utcnow()
                # get the timestamp into seconds, and sleep until its complete
                if time > now:
                    sleep_until: int = (data['expired'] - now).total_seconds()
                    _log.warning(f"sleeping for  {sleep_until} seconds")
                    await asyncio.sleep(sleep_until)
                    # handle the events
                    await self.HandelEvent(data)
                else:
                    await self._DeleteColumn(data)
        except asyncio.CancelledError as e:
            _log.error(e)
        except (OSError, asyncpg.PostgresConnectionError):
            self._tasks.cancel()
            self._tasks = self.LoadTasks()
        except Exception as e:
            # print the Exception
            traceback.print_exception(type(e), e, e.__traceback__, file=sys.stderr)

    async def GetData(self):
        """ Return the data"""
        data = await self.database.Select(
            timedelta(days=40),
            table="peep.inv",
            columns="*",
            condition="expired < (CURRENT_DATE + $1::interval)",
            row=True,
            Filter="ORDER BY expired LIMIT 1"
        )
        self.current_data = data
        return data

    async def Get_initialize_data(self):
        """
        returns data if it exists
        else its wait the data until its initialize
        :return: asyncpg record contains user inventory data
        """
        data = await self.GetData()
        if data:
            self._next_data.set()
            return data
        self._next_data.clear()
        await self._next_data.wait()
        data = await self.GetData()
        return data

    async def HandelEvent(self, data):
        await self._DeleteColumn(data)

    async def _DeleteColumn(self, data):
        try:
            await self.database.Delete(
                data['items'],
                table='peep.inv',
                condition='items = $1'
            )
        except Exception as e:
            _log.info(e)

    async def ReloadTask(self):
        """ reinitialize the tasks"""
        self._tasks.cancel()
        self._tasks = self.LoadTasks()

    async def SetTasks(self):
        """ resume waiting tasks """
        self._next_data.set()
