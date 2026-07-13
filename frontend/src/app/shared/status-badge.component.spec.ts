import { ComponentFixture, TestBed } from '@angular/core/testing';

import { STATUS_META } from '../core/status';
import { StatusBadgeComponent } from './status-badge.component';

describe('StatusBadgeComponent', () => {
  let fixture: ComponentFixture<StatusBadgeComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [StatusBadgeComponent],
    }).compileComponents();
    fixture = TestBed.createComponent(StatusBadgeComponent);
  });

  it('renders the label and glyph, and applies the tone chip class', () => {
    fixture.componentRef.setInput('meta', STATUS_META['effective']);
    fixture.detectChanges();
    const el: HTMLElement = fixture.nativeElement;
    expect(el.textContent).toContain('Effective');
    expect(el.textContent).toContain(STATUS_META['effective'].glyph);
    // tone 'ok' -> ok chip classes present
    expect(el.querySelector('span')?.className).toContain('bg-ok-soft');
  });
});
