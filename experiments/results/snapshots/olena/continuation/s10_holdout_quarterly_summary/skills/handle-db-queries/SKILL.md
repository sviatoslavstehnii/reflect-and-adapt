# Handle DB Queries

## Trigger
User asks to run, execute, or check something directly against a live database (e.g., Postgres).

## Steps
1. Politely remind the user that you do not have direct execution access to their live database.
2. Offer to write, optimize, or debug the SQL query for them to execute manually.
3. Request the relevant database schema, table structures, or SQL dialect (e.g., Postgres) if not already provided in the context.
4. Generate the requested SQL query with clear comments and formatting.

## Notes
- Never pretend to execute the query or simulate a database response.
- Always ensure the generated SQL matches the user's specific dialect (e.g., PostgreSQL).
