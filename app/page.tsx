import Link from "next/link";
import {
  ArrowRight, Bot, Crosshair, Database, Brain, Map, ShieldAlert,
} from "lucide-react";

const MODULES = [
  {
    href: "/detection",
    icon: Crosshair,
    title: "Vision Engine",
    description:
      "Upload surveillance imagery for YOLO object detection, mapped onto a military threat taxonomy.",
  },
  {
    href: "/predictive",
    icon: Brain,
    title: "Predictive Intel",
    description:
      "Score telemetry with a gradient-boosted model across object, terrain, weather, time and proximity.",
  },
  {
    href: "/maps",
    icon: Map,
    title: "GIS Tactical Map",
    description:
      "Threat markers, patrol units and sensor coverage rendered over a dark tactical basemap.",
  },
  {
    href: "/data",
    icon: Database,
    title: "Data Hub",
    description:
      "Analytics computed from recorded activity, with one-click PDF situation report export.",
  },
  {
    href: "/assistant",
    icon: Bot,
    title: "AI Assistant",
    description:
      "Ask questions about recorded telemetry and draft situational reports, grounded in stored records.",
  },
  {
    href: "/history",
    icon: ShieldAlert,
    title: "Threat Intelligence",
    description:
      "Full detection history with confidence scores, source classes and analyst review status.",
  },
];

export default function Home() {
  return (
    <div className="space-y-12 pb-8">
      <section className="pt-6 sm:pt-12">
        <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-white/5 border border-white/10 text-aegis-accent text-sm font-semibold mb-5">
          <ShieldAlert className="w-4 h-4" aria-hidden="true" />
          <span>Decision support, not decision making</span>
        </div>

        <h1 className="text-4xl sm:text-5xl lg:text-6xl font-extrabold tracking-tight max-w-4xl">
          Turning surveillance data into{" "}
          <span className="text-gradient">actionable intelligence</span>
        </h1>

        <p className="mt-6 text-lg text-gray-300 max-w-2xl leading-relaxed">
          AegisAI combines computer vision, machine-learning threat scoring, GIS
          visualisation and generative analysis into one analyst workspace. Every
          score is advisory, every input is recorded, and every output is
          auditable.
        </p>

        <div className="mt-8 flex flex-col sm:flex-row gap-4">
          <Link
            href="/dashboard"
            className="inline-flex items-center justify-center gap-2 px-6 py-3.5 rounded-xl bg-gradient-to-r from-aegis-accent to-aegis-accent-secondary text-aegis-bg font-bold hover:opacity-90 transition-opacity"
          >
            Open dashboard
            <ArrowRight className="w-5 h-5" aria-hidden="true" />
          </Link>
          <Link
            href="/security"
            className="inline-flex items-center justify-center gap-2 px-6 py-3.5 rounded-xl bg-white/5 border border-white/15 text-white font-semibold hover:bg-white/10 transition-colors"
          >
            Sign in
          </Link>
        </div>
      </section>

      <section aria-labelledby="modules-heading">
        <h2 id="modules-heading" className="text-2xl font-bold text-white mb-6">
          Platform modules
        </h2>
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {MODULES.map(({ href, icon: Icon, title, description }) => (
            <Link
              key={href}
              href={href}
              className="glass-panel rounded-2xl p-6 group hover:border-aegis-accent/40 transition-colors"
            >
              <div className="w-11 h-11 rounded-xl bg-white/5 flex items-center justify-center text-aegis-accent mb-4 group-hover:bg-aegis-accent/15 transition-colors">
                <Icon className="w-5 h-5" aria-hidden="true" />
              </div>
              <h3 className="text-lg font-bold text-white mb-2">{title}</h3>
              <p className="text-sm text-gray-400 leading-relaxed">{description}</p>
            </Link>
          ))}
        </div>
      </section>

      {/* Being straight about what this is matters more than looking impressive. */}
      <section className="glass-panel rounded-2xl p-6 border-l-4 border-aegis-warning">
        <h2 className="text-lg font-bold text-white mb-2">Demonstration system</h2>
        <p className="text-sm text-gray-300 leading-relaxed max-w-3xl">
          Threat scores come from a model trained on <strong>synthetic</strong>{" "}
          telemetry, and object detection uses stock COCO-trained YOLO weights
          mapped onto military classes as a documented proxy. Neither is suitable
          for operational use. See{" "}
          <code className="px-1.5 py-0.5 rounded bg-white/10 text-aegis-accent text-xs">
            docs/architecture.md
          </code>{" "}
          for the full caveats.
        </p>
      </section>
    </div>
  );
}
