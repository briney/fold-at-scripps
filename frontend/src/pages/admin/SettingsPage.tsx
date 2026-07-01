import { useEffect, type JSX } from "react";

import { zodResolver } from "@hookform/resolvers/zod";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import ErrorState from "@/components/states/ErrorState";
import Loading from "@/components/states/Loading";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useAdminSettings, useUpdateSettings } from "@/hooks/use-admin-settings";
import type { SystemSettingsRead, SystemSettingsUpdate } from "@/types/api";

const runsField = z
  .number({ message: "Enter a whole number" })
  .int("Enter a whole number")
  .min(0, "Must be zero or greater");

const settingsSchema = z.object({
  maintenance_mode: z.boolean(),
  standard_max_concurrent_runs: runsField,
  power_max_concurrent_runs: runsField,
});

type SettingsValues = z.infer<typeof settingsSchema>;

function toValues(settings: SystemSettingsRead): SettingsValues {
  return {
    maintenance_mode: settings.maintenance_mode,
    standard_max_concurrent_runs: settings.standard_max_concurrent_runs,
    power_max_concurrent_runs: settings.power_max_concurrent_runs,
  };
}

/** Build a partial update containing only fields that changed from the current settings. */
function buildChanges(current: SystemSettingsRead, values: SettingsValues): SystemSettingsUpdate {
  const changes: SystemSettingsUpdate = {};
  if (values.maintenance_mode !== current.maintenance_mode) {
    changes.maintenance_mode = values.maintenance_mode;
  }
  if (values.standard_max_concurrent_runs !== current.standard_max_concurrent_runs) {
    changes.standard_max_concurrent_runs = values.standard_max_concurrent_runs;
  }
  if (values.power_max_concurrent_runs !== current.power_max_concurrent_runs) {
    changes.power_max_concurrent_runs = values.power_max_concurrent_runs;
  }
  return changes;
}

interface SettingsFormProps {
  settings: SystemSettingsRead;
}

function SettingsForm({ settings }: SettingsFormProps): JSX.Element {
  const updateMutation = useUpdateSettings();
  const {
    control,
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<SettingsValues>({
    resolver: zodResolver(settingsSchema),
    defaultValues: toValues(settings),
  });

  // Re-seed the form whenever fresh settings arrive from the server.
  useEffect(() => {
    reset(toValues(settings));
  }, [settings, reset]);

  function onSubmit(values: SettingsValues): void {
    updateMutation.mutate(buildChanges(settings, values));
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate>
      <CardContent className="space-y-6">
        <div className="flex items-center justify-between gap-4">
          <div className="space-y-1">
            <Label htmlFor="maintenance_mode">Maintenance mode</Label>
            <p className="text-sm text-muted-foreground">
              When enabled, non-admin users cannot submit new runs.
            </p>
          </div>
          <Controller
            control={control}
            name="maintenance_mode"
            render={({ field }) => (
              <Switch
                id="maintenance_mode"
                checked={field.value}
                onCheckedChange={field.onChange}
              />
            )}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="standard_max_concurrent_runs">Standard tier max concurrent runs</Label>
          <Input
            id="standard_max_concurrent_runs"
            type="number"
            min={0}
            {...register("standard_max_concurrent_runs", { valueAsNumber: true })}
          />
          {errors.standard_max_concurrent_runs ? (
            <p className="text-sm text-destructive">
              {errors.standard_max_concurrent_runs.message}
            </p>
          ) : null}
        </div>
        <div className="space-y-2">
          <Label htmlFor="power_max_concurrent_runs">Power tier max concurrent runs</Label>
          <Input
            id="power_max_concurrent_runs"
            type="number"
            min={0}
            {...register("power_max_concurrent_runs", { valueAsNumber: true })}
          />
          {errors.power_max_concurrent_runs ? (
            <p className="text-sm text-destructive">{errors.power_max_concurrent_runs.message}</p>
          ) : null}
        </div>
      </CardContent>
      <CardFooter>
        <Button type="submit" disabled={updateMutation.isPending}>
          Save
        </Button>
      </CardFooter>
    </form>
  );
}

/** Admin screen for editing system-wide settings: maintenance mode and per-tier quotas. */
export default function SettingsPage(): JSX.Element {
  const { data, isLoading, isError, refetch } = useAdminSettings();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="text-sm text-muted-foreground">
          Manage system-wide maintenance mode and per-tier run quotas.
        </p>
      </div>

      {isLoading ? (
        <Loading label="Loading settings" />
      ) : isError || !data ? (
        <ErrorState message="Failed to load settings." onRetry={() => void refetch()} />
      ) : (
        <Card className="max-w-2xl">
          <CardHeader>
            <CardTitle>System settings</CardTitle>
            <CardDescription>Changes take effect immediately after saving.</CardDescription>
          </CardHeader>
          <SettingsForm settings={data} />
        </Card>
      )}
    </div>
  );
}
