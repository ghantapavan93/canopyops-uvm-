import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    loadComponent: () =>
      import('./features/landing/landing.component').then((m) => m.LandingComponent),
    title: 'CanopyOps — Treatment Assurance',
  },
  {
    path: 'login',
    loadComponent: () =>
      import('./features/auth/login.component').then((m) => m.LoginComponent),
    title: 'Sign in — CanopyOps',
  },
  {
    path: 'vision',
    loadComponent: () =>
      import('./features/vision/vision.component').then((m) => m.VisionComponent),
    title: 'Future Vision — CanopyOps',
  },
  {
    path: 'report',
    loadComponent: () =>
      import('./features/report/report.component').then((m) => m.ReportComponent),
    title: 'Compliance Report — CanopyOps',
  },
  {
    path: 'console',
    loadComponent: () =>
      import('./features/console/console-shell.component').then(
        (m) => m.ConsoleShellComponent,
      ),
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'overview' },
      {
        path: 'overview',
        loadComponent: () =>
          import('./features/overview/overview.component').then((m) => m.OverviewComponent),
        title: 'Program Overview — CanopyOps',
      },
      {
        path: 'command',
        loadComponent: () =>
          import('./features/command-center/command-center.component').then(
            (m) => m.CommandCenterComponent,
          ),
        title: 'Command Center — CanopyOps',
      },
      {
        path: 'plan',
        loadComponent: () =>
          import('./features/plan-builder/plan-builder.component').then(
            (m) => m.PlanBuilderComponent,
          ),
        title: 'Treatment Plan Builder — CanopyOps',
      },
      {
        path: 'execution',
        loadComponent: () =>
          import('./features/field-execution/field-execution.component').then(
            (m) => m.FieldExecutionComponent,
          ),
        title: 'Field Execution — CanopyOps',
      },
      {
        path: 'sync',
        loadComponent: () =>
          import('./features/sync-center/sync-center.component').then(
            (m) => m.SyncCenterComponent,
          ),
        title: 'Sync & Conflict Center — CanopyOps',
      },
      {
        path: 'verification',
        loadComponent: () =>
          import('./features/verification/verification.component').then(
            (m) => m.VerificationComponent,
          ),
        title: 'Outcome Verification — CanopyOps',
      },
      {
        path: 'stewardship',
        loadComponent: () =>
          import('./features/stewardship/stewardship.component').then(
            (m) => m.StewardshipComponent,
          ),
        title: 'Stewardship & Compliance — CanopyOps',
      },
      {
        path: 'risk',
        loadComponent: () =>
          import('./features/risk/risk.component').then((m) => m.RiskComponent),
        title: 'Risk Intelligence — CanopyOps',
      },
      {
        path: 'vegetation',
        loadComponent: () =>
          import('./features/vegetation/vegetation.component').then(
            (m) => m.VegetationComponent,
          ),
        title: 'Vegetation Intelligence — CanopyOps',
      },
      {
        path: 'audit',
        loadComponent: () =>
          import('./features/audit/audit.component').then((m) => m.AuditComponent),
        title: 'Quality & Compliance — CanopyOps',
      },
      {
        path: 'geofence',
        loadComponent: () =>
          import('./features/geofence/geofence.component').then(
            (m) => m.GeofenceComponent,
          ),
        title: 'Field Safety · Geofencing — CanopyOps',
      },
      {
        path: 'terrain',
        loadComponent: () =>
          import('./features/terrain/terrain.component').then(
            (m) => m.TerrainComponent,
          ),
        title: '3D Terrain — CanopyOps',
      },
      {
        path: 'integration',
        loadComponent: () =>
          import('./features/integration-odata/integration-odata.component').then(
            (m) => m.IntegrationOdataComponent,
          ),
        title: 'Integration · OData — CanopyOps',
      },
      {
        path: 'engineering',
        loadComponent: () =>
          import('./features/engineering/engineering.component').then(
            (m) => m.EngineeringComponent,
          ),
        title: 'Engineering Evidence — CanopyOps',
      },
    ],
  },
  {
    path: '**',
    loadComponent: () =>
      import('./features/not-found/not-found.component').then((m) => m.NotFoundComponent),
    title: 'Not found — CanopyOps',
  },
];
