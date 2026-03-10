"""Add SHADOW_START and SHADOW_END to the PostgreSQL authaction enum."""
import asyncio
from sqlalchemy import text

async def main():
    from src.database import engine
    async with engine.begin() as conn:
        result = await conn.execute(text(
            "SELECT enumlabel FROM pg_enum "
            "JOIN pg_type ON pg_enum.enumtypid = pg_type.oid "
            "WHERE pg_type.typname = 'authaction' "
            "ORDER BY enumsortorder"
        ))
        existing = [row[0] for row in result.fetchall()]
        print(f"Existing enum values: {existing}")

        for val in ["SHADOW_START", "SHADOW_END"]:
            if val not in existing:
                await conn.execute(text(f"ALTER TYPE authaction ADD VALUE '{val}'"))
                print(f"Added: {val}")
            else:
                print(f"Already exists: {val}")

    await engine.dispose()
    print("Done!")

if __name__ == "__main__":
    asyncio.run(main())
