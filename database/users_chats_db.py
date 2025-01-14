import motor.motor_asyncio
from info import DATABASE_NAME, DATABASE_URI

class Database:

    def __init__(self, uri, database_name):
        self._client = motor.motor_asyncio.AsyncIOMotorClient(uri)
        self.db = self._client[database_name]
        self.col = self.db.users

    def new_user(self, id, name):
        return dict(
            id=id,
            name=name,
            banned=False  # Default to not banned
        )
    
    async def add_user(self, id, name):
        user = self.new_user(id, name)
        await self.col.insert_one(user)
    
    async def is_user_exist(self, id):
        user = await self.col.find_one({'id': int(id)})
        return bool(user)
    
    async def total_users_count(self):
        count = await self.col.count_documents({})
        return count

    async def get_all_users(self):
        return self.col.find({})

    async def delete_user(self, user_id):
        await self.col.delete_many({'id': int(user_id)})

    async def ban_user(self, user_id):
        """Ban a user by updating their banned status in the database."""
        result = await self.col.update_one(
            {'id': int(user_id)}, 
            {'$set': {'banned': True}}
        )
        return result.modified_count > 0

    async def unban_user(self, user_id):
        """Unban a user by updating their banned status in the database."""
        result = await self.col.update_one(
            {'id': int(user_id)}, 
            {'$set': {'banned': False}}
        )
        return result.modified_count > 0

    async def is_user_banned(self, user_id):
        """Check if a user is banned."""
        user = await self.col.find_one({'id': int(user_id)})
        return user['banned'] if user else False

db = Database(DATABASE_URI, DATABASE_NAME)
