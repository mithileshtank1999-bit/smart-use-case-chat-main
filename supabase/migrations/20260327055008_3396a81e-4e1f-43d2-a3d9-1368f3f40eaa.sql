
CREATE TABLE public.projects (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id text UNIQUE NOT NULL,
  project_name text NOT NULL,
  account_id text,
  account_name text,
  portfolio_name text,
  portfolio_owner text,
  status text DEFAULT 'Active',
  go_live_date date,
  project_manager text,
  created_at timestamptz DEFAULT now()
);

ALTER TABLE public.projects ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow public read access to projects"
ON public.projects
FOR SELECT
TO public
USING (true);

INSERT INTO public.projects (project_id, project_name, account_id, account_name, portfolio_name, portfolio_owner, status, go_live_date, project_manager) VALUES
('PRJ001', 'Core Banking Transformation', 'ACC001', 'ABC Bank', 'Banking Portfolio', 'John Smith', 'Active', '2026-09-15', 'Alice Johnson'),
('PRJ002', 'Digital Payments Gateway', 'ACC001', 'ABC Bank', 'Banking Portfolio', 'John Smith', 'Active', '2026-06-30', 'Bob Williams'),
('PRJ003', 'Insurance Claims Portal', 'ACC002', 'XYZ Insurance', 'Insurance Portfolio', 'Sarah Davis', 'In Progress', '2026-12-01', 'Carol Martinez'),
('PRJ004', 'Wealth Management Platform', 'ACC003', 'Global Wealth Corp', 'Banking Portfolio', 'John Smith', 'Delayed', '2026-03-31', 'David Brown'),
('PRJ005', 'Regulatory Compliance System', 'ACC001', 'ABC Bank', 'Compliance Portfolio', 'Mike Wilson', 'Active', '2026-08-15', 'Eve Taylor'),
('PRJ006', 'Customer Onboarding App', 'ACC004', 'FinTech Solutions', 'Digital Portfolio', 'Lisa Anderson', 'Completed', '2025-12-31', 'Frank Thomas'),
('PRJ007', 'Risk Analytics Dashboard', 'ACC002', 'XYZ Insurance', 'Insurance Portfolio', 'Sarah Davis', 'Active', '2026-11-30', 'Grace Lee'),
('PRJ008', 'Mobile Banking 2.0', 'ACC001', 'ABC Bank', 'Digital Portfolio', 'Lisa Anderson', 'In Progress', '2026-07-15', 'Henry Clark'),
('PRJ009', 'Trade Finance Platform', 'ACC005', 'Trade Corp International', 'Banking Portfolio', 'John Smith', 'Active', '2027-01-15', 'Ivy Robinson'),
('PRJ010', 'HR Management System', 'ACC003', 'Global Wealth Corp', 'Internal Portfolio', 'Robert King', 'On Hold', '2026-10-01', 'Jack White');
