import { JsonPipe } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';

import {
  OdataBatchRequest,
  OdataBatchResult,
  OdataQuery,
  OdataResult,
  OdataService,
} from '../../core/odata.service';

interface WbsRow {
  Wbs: string;
  Circuit?: string;
  Span?: string;
  Status?: string;
  Priority?: string;
  EvidenceScore?: number;
  CoverageRatio?: number | null;
  'CatsEntries@odata.navigationLink'?: string;
}
interface CatsRow {
  CatsId: string;
  PersonnelName: string;
  WorkDate: string;
  Hours: number;
  ActivityType: string;
}

const FILTERS: { key: string; label: string; filter?: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'awaiting', label: "Status eq 'awaiting_verification'", filter: "Status eq 'awaiting_verification'" },
  { key: 'hazard', label: "Priority eq 'hazard'", filter: "Priority eq 'hazard'" },
  { key: 'complete', label: 'EvidenceComplete eq true', filter: 'EvidenceComplete eq true' },
];

const ORDERBY: { key: string; label: string; orderby?: string }[] = [
  { key: 'wbs', label: 'Wbs', orderby: 'Wbs' },
  { key: 'evidence', label: 'EvidenceScore desc', orderby: 'EvidenceScore desc' },
  { key: 'status', label: 'Status', orderby: 'Status' },
  { key: 'priority', label: 'Priority', orderby: 'Priority' },
];

/** Integration (OData / SAP) — demonstrates the seam Davey's Angular developers
 *  actually work: an Angular front end consuming an SAP-style OData service.
 *  Shows WBS elements + deferred CATS expansion + live cache/ETag telemetry. */
@Component({
  selector: 'app-integration-odata',
  standalone: true,
  imports: [JsonPipe],
  templateUrl: './integration-odata.component.html',
})
export class IntegrationOdataComponent {
  private odata = inject(OdataService);

  readonly filters = FILTERS;
  readonly orderbys = ORDERBY;

  readonly filterKey = signal('all');
  readonly orderbyKey = signal('wbs');
  readonly skip = signal(0);

  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly result = signal<OdataResult<WbsRow> | null>(null);
  readonly rawOpen = signal(false);

  // deferred CATS expansion, keyed by WBS
  readonly expandedKey = signal<string | null>(null);
  readonly cats = signal<OdataResult<CatsRow> | null>(null);

  readonly rows = computed(() => this.result()?.value ?? []);
  readonly metadataUrl = this.odata.url('$metadata');

  private query(): OdataQuery {
    return {
      select: 'Wbs,Circuit,Span,Status,Priority,EvidenceScore,CoverageRatio',
      filter: this.filters.find((f) => f.key === this.filterKey())?.filter,
      orderby: this.orderbys.find((o) => o.key === this.orderbyKey())?.orderby,
      skip: this.skip() || undefined,
    };
  }
  private currentPath(): string {
    return this.odata.buildPath('WbsElements', this.query());
  }
  rawUrl = () => this.odata.url(this.currentPath());

  constructor() {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.expandedKey.set(null);
    this.odata.query<WbsRow>(this.currentPath()).subscribe({
      next: (r) => { this.result.set(r); this.loading.set(false); },
      error: (e) => { this.error.set(e?.message ?? 'OData request failed'); this.loading.set(false); },
    });
  }

  /** Re-runs the exact same query — with an ETag cached, this returns 304. */
  refetch(): void { this.load(); }

  setFilter(key: string): void { this.filterKey.set(key); this.skip.set(0); this.load(); }
  setOrderby(key: string): void { this.orderbyKey.set(key); this.skip.set(0); this.load(); }

  nextPage(): void {
    const link = this.result()?.nextLink;
    if (!link) return;
    this.skip.update((s) => s + 5);
    this.load();
  }
  prevPage(): void {
    if (this.skip() <= 0) return;
    this.skip.update((s) => Math.max(0, s - 5));
    this.load();
  }

  /** Deferred loading: only NOW do we fetch the navigation property. */
  expandCats(row: WbsRow): void {
    if (this.expandedKey() === row.Wbs) { this.expandedKey.set(null); return; }
    const link = row['CatsEntries@odata.navigationLink'] ?? `WbsElements('${row.Wbs}')/CatsEntries`;
    this.expandedKey.set(row.Wbs);
    this.cats.set(null);
    this.odata.query<CatsRow>(link).subscribe({
      next: (r) => this.cats.set(r),
      error: () => this.cats.set(null),
    });
  }

  pct(v: number | null | undefined): string {
    return v == null ? '—' : `${Math.round(v * 100)}%`;
  }

  // --- $batch: many reads, one round-trip ---------------------------------
  readonly batchLoading = signal(false);
  readonly batchResult = signal<OdataBatchResult | null>(null);
  readonly batchRequests = computed<OdataBatchRequest[]>(() => {
    const first = this.rows()[0]?.Wbs;
    return [
      { id: 'wbs-page', method: 'GET', url: 'WbsElements?$top=3&$count=true' },
      { id: 'confirmed-cats', method: 'GET', url: 'CatsEntries?$filter=Confirmed eq true' },
      ...(first ? [{ id: 'detail-cats', method: 'GET', url: `WbsElements('${first}')/CatsEntries` } as OdataBatchRequest] : []),
    ];
  });

  runBatch(): void {
    this.batchLoading.set(true);
    this.batchResult.set(null);
    this.odata.batch(this.batchRequests()).subscribe({
      next: (r) => { this.batchResult.set(r); this.batchLoading.set(false); },
      error: () => this.batchLoading.set(false),
    });
  }

  /** A one-line human summary of a sub-response for the results strip. */
  batchSummary(r: { status: number; body: any }): string {
    const b = r.body ?? {};
    if (b.error) return b.error.message ?? `error ${r.status}`;
    if (typeof b['@odata.count'] === 'number') return `${b.value?.length ?? 0} of ${b['@odata.count']} rows`;
    if (Array.isArray(b.value)) return `${b.value.length} rows`;
    if (b.Wbs) return b.Wbs;
    return 'ok';
  }
}
