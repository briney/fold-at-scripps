import type { JSX } from "react";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, login } from "@/lib/api";

const loginSchema = z.object({
  email: z.string().email("Enter a valid email address"),
  password: z.string().min(1, "Password is required"),
});

type LoginValues = z.infer<typeof loginSchema>;

interface LocationState {
  from?: { pathname?: string };
}

/** Public login page: authenticates the user and navigates to the app. */
export default function LoginPage(): JSX.Element {
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const from = (location.state as LocationState | null)?.from?.pathname ?? "/";

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginValues>({ resolver: zodResolver(loginSchema) });

  const mutation = useMutation({
    mutationFn: (values: LoginValues) => login(values.email, values.password),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["me"] });
      navigate(from, { replace: true });
    },
  });

  const apiError = mutation.error instanceof ApiError ? mutation.error.detail : undefined;

  function onSubmit(values: LoginValues): void {
    mutation.mutate(values);
  }

  return (
    <div className="flex min-h-svh items-center justify-center p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <h1 className="font-semibold leading-none tracking-tight">Log in</h1>
          <CardDescription>Sign in to your fold@Scripps account.</CardDescription>
        </CardHeader>
        <form onSubmit={handleSubmit(onSubmit)} noValidate>
          <CardContent className="space-y-4">
            {apiError ? (
              <p role="alert" className="text-sm text-destructive">
                {apiError}
              </p>
            ) : null}
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input id="email" type="email" autoComplete="email" {...register("email")} />
              {errors.email ? (
                <p className="text-sm text-destructive">{errors.email.message}</p>
              ) : null}
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                {...register("password")}
              />
              {errors.password ? (
                <p className="text-sm text-destructive">{errors.password.message}</p>
              ) : null}
            </div>
          </CardContent>
          <CardFooter className="flex flex-col items-stretch gap-3">
            <Button type="submit" disabled={mutation.isPending}>
              Log in
            </Button>
            <div className="flex justify-between text-sm text-muted-foreground">
              <Link to="/register" className="underline-offset-4 hover:underline">
                Register
              </Link>
              <Link to="/reset-password" className="underline-offset-4 hover:underline">
                Reset password
              </Link>
            </div>
          </CardFooter>
        </form>
      </Card>
    </div>
  );
}
