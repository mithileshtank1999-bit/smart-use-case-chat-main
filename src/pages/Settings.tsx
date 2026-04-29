import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { supabase } from "@/integrations/supabase/client";
import { apiCall, getApiBaseUrl } from "@/lib/apiClient";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { toast } from "sonner";
import { ArrowLeft, Database, Loader2, CheckCircle2, XCircle } from "lucide-react";

interface ConnectionForm {
  connection_name: string;
  db_type: "sqlserver" | "postgres";
  host: string;
  port: string;
  database_name: string;
  username: string;
  password: string;
}

const defaultForm: ConnectionForm = {
  connection_name: "Default",
  db_type: "sqlserver",
  host: "",
  port: "1433",
  database_name: "",
  username: "",
  password: "",
};

const isLocal = () => !!getApiBaseUrl();

const Settings = () => {
  const navigate = useNavigate();
  const [form, setForm] = useState<ConnectionForm>(defaultForm);
  const [existingId, setExistingId] = useState<string | null>(null);
  const [isTesting, setIsTesting] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<"idle" | "success" | "error">("idle");

  useEffect(() => {
    (async () => {
      if (isLocal()) {
        const { data } = await apiCall("db-connections", undefined, { method: "GET" });
        if (data?.data) {
          const d = data.data;
          setExistingId(d.id);
          setForm({
            connection_name: d.connection_name,
            db_type: d.db_type as "sqlserver" | "postgres",
            host: d.host,
            port: String(d.port),
            database_name: d.database_name,
            username: d.username,
            password: "",
          });
          setConnectionStatus("success");
        }
      } else {
        const { data } = await supabase
          .from("db_connections")
          .select("*")
          .eq("is_active", true)
          .limit(1)
          .single();
        if (data) {
          setExistingId(data.id);
          setForm({
            connection_name: data.connection_name,
            db_type: (data.db_type === "postgres" ? "postgres" : "sqlserver") as "sqlserver" | "postgres",
            host: data.host,
            port: String(data.port),
            database_name: data.database_name,
            username: data.username,
            password: "",
          });
          setConnectionStatus("success");
        }
      }
    })();
  }, []);

  const handleChange = (field: keyof ConnectionForm, value: string) => {
    setForm((prev) => {
      const updated = { ...prev, [field]: value };
      if (field === "db_type") {
        const oldDefault = prev.db_type === "postgres" ? "5432" : "1433";
        const newDefault = value === "postgres" ? "5432" : "1433";
        if (prev.port === oldDefault || prev.port === "") {
          updated.port = newDefault;
        }
      }
      return updated;
    });
    setConnectionStatus("idle");
  };

  const handleTestConnection = async () => {
    if (!form.host || !form.database_name || !form.username) {
      toast.error("Please fill in all required fields");
      return;
    }

    setIsTesting(true);
    setConnectionStatus("idle");

    try {
      if (!isLocal()) {
        await saveConnection(false);
      }

      const { data, error } = await apiCall("db-proxy", { query_type: "test_connection" });
      if (error) throw new Error(error.message);
      if (data?.error) throw new Error(data.error);

      setConnectionStatus("success");
      toast.success("Connection successful!");
    } catch (err: any) {
      setConnectionStatus("error");
      toast.error(`Connection failed: ${err.message}`);
    } finally {
      setIsTesting(false);
    }
  };

  const saveConnection = async (showToast = true) => {
    const defaultPort = form.db_type === "postgres" ? 5432 : 1433;
    const payload: Record<string, unknown> = {
      connection_name: form.connection_name || "Default",
      host: form.host,
      port: parseInt(form.port) || defaultPort,
      database_name: form.database_name,
      username: form.username,
      encrypted_password: form.password,
      db_type: form.db_type,
      is_active: isLocal() ? 1 : true,
    };

    if (isLocal()) {
      if (existingId) payload.id = existingId;
      if (!existingId && !form.password) throw new Error("Password is required for new connections");
      const { data, error } = await apiCall("db-connections", payload);
      if (error) throw new Error(error.message);
      if (data?.id && !existingId) setExistingId(data.id);
    } else {
      if (existingId) {
        const updatePayload = form.password
          ? payload
          : { ...payload, encrypted_password: undefined };
        const { error } = await supabase
          .from("db_connections")
          .update(updatePayload)
          .eq("id", existingId);
        if (error) throw error;
      } else {
        if (!form.password) throw new Error("Password is required for new connections");
        const { data, error } = await supabase
          .from("db_connections")
          .insert(payload as any)
          .select("id")
          .single();
        if (error) throw error;
        if (data) setExistingId(data.id);
      }
    }

    if (showToast) toast.success("Connection saved!");
  };

  const handleSave = async () => {
    if (!form.host || !form.database_name || !form.username) {
      toast.error("Please fill in all required fields");
      return;
    }

    setIsSaving(true);
    try {
      await saveConnection(true);
    } catch (err: any) {
      toast.error(`Save failed: ${err.message}`);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="min-h-screen bg-background">
      <header className="h-14 flex items-center gap-3 border-b px-4 bg-background/80 backdrop-blur-sm">
        <Button variant="ghost" size="icon" onClick={() => navigate("/")}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div className="flex items-center gap-2">
          <div className="h-7 w-7 rounded-lg bg-primary flex items-center justify-center">
            <Database className="h-4 w-4 text-primary-foreground" />
          </div>
          <h1 className="text-base font-semibold text-foreground">Database Settings</h1>
        </div>
      </header>

      <div className="max-w-2xl mx-auto p-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Database className="h-5 w-5" />
              Database Connection
            </CardTitle>
            <CardDescription>
              Connect your external database to fetch real project data.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="connection_name">Connection Name</Label>
                <Input
                  id="connection_name"
                  value={form.connection_name}
                  onChange={(e) => handleChange("connection_name", e.target.value)}
                  placeholder="Default"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="db_type">Database Type *</Label>
                <select
                  id="db_type"
                  value={form.db_type}
                  onChange={(e) => handleChange("db_type", e.target.value)}
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                >
                  <option value="sqlserver">SQL Server</option>
                  <option value="postgres">PostgreSQL</option>
                </select>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-4">
              <div className="col-span-2 space-y-2">
                <Label htmlFor="host">Host *</Label>
                <Input
                  id="host"
                  value={form.host}
                  onChange={(e) => handleChange("host", e.target.value)}
                  placeholder="e.g. myserver.database.windows.net"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="port">Port</Label>
                <Input
                  id="port"
                  value={form.port}
                  onChange={(e) => handleChange("port", e.target.value)}
                  placeholder="1433"
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="database_name">Database Name *</Label>
              <Input
                id="database_name"
                value={form.database_name}
                onChange={(e) => handleChange("database_name", e.target.value)}
                placeholder="e.g. ProjectDB"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="username">Username *</Label>
                <Input
                  id="username"
                  value={form.username}
                  onChange={(e) => handleChange("username", e.target.value)}
                  placeholder="sa"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="password">Password {existingId ? "(leave blank to keep current)" : "*"}</Label>
                <Input
                  id="password"
                  type="password"
                  value={form.password}
                  onChange={(e) => handleChange("password", e.target.value)}
                  placeholder="••••••••"
                />
              </div>
            </div>

            {connectionStatus !== "idle" && (
              <div className={`flex items-center gap-2 p-3 rounded-md text-sm ${
                connectionStatus === "success"
                  ? "bg-green-50 text-green-700 border border-green-200"
                  : "bg-red-50 text-red-700 border border-red-200"
              }`}>
                {connectionStatus === "success" ? (
                  <><CheckCircle2 className="h-4 w-4" /> Connected successfully</>
                ) : (
                  <><XCircle className="h-4 w-4" /> Connection failed</>
                )}
              </div>
            )}

            <div className="flex gap-3 pt-2">
              <Button
                variant="outline"
                onClick={handleTestConnection}
                disabled={isTesting || isSaving}
              >
                {isTesting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                Test Connection
              </Button>
              <Button onClick={handleSave} disabled={isSaving || isTesting}>
                {isSaving && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                Save Connection
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default Settings;
