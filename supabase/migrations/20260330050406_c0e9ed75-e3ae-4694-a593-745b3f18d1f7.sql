CREATE TABLE public.db_connections (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  connection_name text NOT NULL DEFAULT 'Default',
  host text NOT NULL,
  port integer NOT NULL DEFAULT 1433,
  database_name text NOT NULL,
  username text NOT NULL,
  encrypted_password text NOT NULL,
  db_type text NOT NULL DEFAULT 'sqlserver',
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamp with time zone NOT NULL DEFAULT now()
);

ALTER TABLE public.db_connections ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow all access to db_connections" ON public.db_connections FOR ALL TO public USING (true) WITH CHECK (true);