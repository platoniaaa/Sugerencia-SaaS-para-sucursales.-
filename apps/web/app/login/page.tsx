"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Input, Label } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api-client";
import { estaAutenticado } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [entrando, setEntrando] = useState(false);

  useEffect(() => {
    if (estaAutenticado()) router.replace("/");
  }, [router]);

  const ingresar = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setEntrando(true);
    try {
      await api.login(email.trim().toLowerCase(), password);
      router.replace("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo iniciar sesión");
    } finally {
      setEntrando(false);
    }
  };

  return (
    <div className="flex min-h-[80vh] items-center justify-center">
      <div className="w-full max-w-sm rounded-xl border border-slate-200 bg-white p-7 shadow-sm">
        <div className="mb-6 flex flex-col items-center gap-2">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/curifor-logo.png" alt="Curifor" className="h-7 w-auto" />
          <p className="text-sm font-medium text-slate-500">Sugerido de Compras</p>
        </div>

        <form onSubmit={ingresar} className="space-y-3">
          <div>
            <Label htmlFor="email">Correo</Label>
            <Input
              id="email"
              type="email"
              autoComplete="username"
              placeholder="tu.correo@curifor.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>
          <div>
            <Label htmlFor="pass">Contraseña</Label>
            <Input
              id="pass"
              type="password"
              autoComplete="current-password"
              placeholder="••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>

          {error && (
            <p className="rounded-md bg-red-50 px-3 py-2 text-[13px] text-red-700">{error}</p>
          )}

          <Button type="submit" className="w-full" disabled={entrando}>
            {entrando ? "Entrando…" : "Iniciar sesión"}
          </Button>
        </form>
      </div>
    </div>
  );
}
