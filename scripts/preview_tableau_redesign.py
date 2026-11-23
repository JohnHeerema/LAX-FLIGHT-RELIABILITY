"""Draw data-driven design previews; these are not Tableau screenshots."""

import csv
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from scripts.redesign_tableau_workbook import ROOT, WIDTH, HEIGHT, NAVY, MUTED, BLUE


def preview(threshold):
    with (ROOT/"data/tableau/overall_comparison_2025.csv").open(newline="") as f:
        overall=next(r for r in csv.DictReader(f) if int(r["Delay Threshold Minutes"])==threshold)
    with (ROOT/"data/tableau/destination_comparison_2025.csv").open(newline="") as f:
        routes=[r for r in csv.DictReader(f) if int(r["Delay Threshold Minutes"])==threshold]
    routes=sorted(routes,key=lambda r:-(int(r["Morning Flights"])+int(r["Evening Flights"])))[:8]
    routes=sorted(routes,key=lambda r:-float(r["Gap pp"]))
    plt.rcParams.update({"font.family":"DejaVu Sans","axes.unicode_minus":False,"svg.fonttype":"none"})
    fig=plt.figure(figsize=(12,9),facecolor="white")

    def text(x,y,value,size=10,color=NAVY,bold=False):
        return fig.text(x/WIDTH,1-y/HEIGHT,value,fontsize=size,color=color,weight="bold" if bold else "normal",va="top",linespacing=1.45)

    def box(x,y,w,h,color="white"):
        fig.add_artist(Rectangle((x/WIDTH,1-(y+h)/HEIGHT),w/WIDTH,h/HEIGHT,transform=fig.transFigure,
                                 facecolor=color,edgecolor="#dce3eb",linewidth=.8,zorder=-1))

    text(24,18,"LAX flights: morning vs. evening",23,bold=True)
    text(24,61,"2025 domestic departures · Morning 06:00–09:59 · Evening 17:00–20:59 · LAX local time",10,MUTED)
    text(24,91,"DATA-DRIVEN DESIGN PREVIEW · Tableau rendering still needs to be checked",8,"#728294")
    text(980,20,"Arrival delay cutoff (minutes)",9,MUTED)
    text(985,49, ("●" if threshold==15 else "○")+" 15",11,BLUE if threshold==15 else MUTED)
    text(985,75, ("●" if threshold==60 else "○")+" 60",11,BLUE if threshold==60 else MUTED)
    box(24,112,690,215)
    text(40,127,"Disrupted flights",16,bold=True)
    text(40,157,f"Canceled, diverted, or arrival ≥{threshold} minutes late",10,MUTED)
    text(40,177,"Compared using the same airline, destination, and month mix",8,MUTED)
    ax=fig.add_axes([94/WIDTH,1-282/HEIGHT,585/WIDTH,90/HEIGHT])
    rates=[float(overall[n])*100 for n in ["Morning Disruption Rate","Evening Disruption Rate"]]
    ax.barh([1,0],rates,color=["#f28e2b",BLUE],height=.44)
    ax.set_yticks([1,0],["Morning","Evening"],fontsize=10,color=MUTED)
    ax.set_xlim(0,25);ax.set_ylim(-.55,1.55)
    ax.set_xticks([0,5,10,15,20,25],["0%","5%","10%","15%","20%","25%"],fontsize=9,color=MUTED)
    ax.grid(axis="x",color="#edf1f5",linewidth=.7);ax.set_axisbelow(True)
    ax.tick_params(axis="both",length=0)
    for spine in ax.spines.values():spine.set_visible(False)
    for y,value in zip([1,0],rates):ax.text(value+.25,y,f"{value:.2f}%",va="center",fontsize=10,color=NAVY)
    ax.set_xlabel("Disruption rate",fontsize=9,color=MUTED,labelpad=7)
    box(738,112,438,215,"#f1f6fc")
    text(756,127,"The evening gap",16,bold=True)
    text(756,157,f"{threshold}-minute arrival-delay cutoff",10,MUTED)
    text(756,185,f"{float(overall['Gap pp']):.2f}",32,BLUE,True)
    text(887,197,"more",21,BLUE,True)
    text(756,240,"evening disruptions per 100\ncomparable flights",13)
    text(756,300,f"Approx. 95% model interval: {float(overall['Gap Interval Lower pp']):.2f} to {float(overall['Gap Interval Upper pp']):.2f} per 100",9,MUTED)
    box(24,348,1152,400)
    text(40,362,"Where is the evening gap largest?",16,bold=True)
    text(40,393,f"{threshold}-minute cutoff · Eight destinations with the most matched flights",10,MUTED)
    text(40,415,"Dots: estimates · Lines: approximate 95% adjusted model intervals",10,MUTED)
    ax=fig.add_axes([242/WIDTH,1-697/HEIGHT,902/WIDTH,242/HEIGHT])
    lower=[float(r["Gap Interval Lower pp"]) for r in routes]
    upper=[float(r["Gap Interval Upper pp"]) for r in routes]
    gaps=[float(r["Gap pp"]) for r in routes]
    colors=[BLUE if r["Direction Evidence"]=="Higher evening rate" else "#8a8382" for r in routes]
    ax.hlines(range(8),lower,upper,color="#9aa8b8",linewidth=2.6,zorder=2)
    ax.scatter(gaps,range(8),c=colors,s=42,zorder=3)
    labels=[r["Destination City"].split(",")[0].replace("Dallas/Fort Worth","Dallas / Fort Worth")+" ("+r["Destination Code"]+")" for r in routes]
    ax.set_yticks(range(8),labels,fontsize=10,color=NAVY)
    ax.set_ylim(7.6,-.6);ax.set_xlim(-6,24)
    ax.set_xticks([-5,0,5,10,15,20],["-5","0","5","10","15","20"],fontsize=9,color=MUTED)
    ax.axvline(0,color="#65798f",linewidth=1.1,zorder=1)
    ax.grid(axis="x",color="#edf1f5",linewidth=.7);ax.set_axisbelow(True)
    ax.tick_params(axis="both",length=0,pad=7)
    for spine in ax.spines.values():spine.set_visible(False)
    for y,value in enumerate(gaps):ax.text(value+.32,y,f"{value:.2f}",va="center",fontsize=9,color=NAVY)
    ax.set_xlabel("Evening minus morning gap (percentage points)",fontsize=10,color=MUTED,labelpad=10)
    text(24,770,"Positive = higher evening disruption rate.  0 = no estimated gap.  Negative = higher morning rate.",9,MUTED)
    text(24,793,"Blue dots: interval above zero.  Gray dots: interval includes zero, so direction is uncertain.",9,MUTED)
    text(886,763,"Direction of the gap",10,MUTED,bold=True)
    text(887,787,"●",11,BLUE);text(905,787,"Higher evening rate",9,MUTED)
    text(887,808,"●",11,"#8a8382");text(905,808,"Uncertain direction",9,MUTED)
    text(24,836,"Source: U.S. DOT/BTS Reporting Carrier On-Time Performance · Domestic LAX departures, 2025",8,MUTED)
    text(24,851,"Overall comparison: 57,464 matched scheduled flights · 64.2% of reported flights in the selected departure windows",8,MUTED)
    text(24,866,"Historical associations; results do not establish causal effects or predict future flights.",8,MUTED)
    text(24,881,"Methods and code: github.com/JohnHeerema/LAX-FLIGHT-RELIABILITY",8,MUTED)
    output=ROOT/f"reports/figures/tableau_redesign_{threshold}.png"
    fig.savefig(output,dpi=150,metadata={"Software":"LAX Flight Reliability — data-driven design preview, not a Tableau render"})
    plt.close(fig)
    return output


if __name__=="__main__":
    for threshold in [15,60]:print(preview(threshold).relative_to(ROOT))
