import { useEffect, useState, useCallback, useRef } from "react";
import ForceGraph2D from "react-force-graph-2d";
import { getGraphEntity } from "../services/api";
import type { GraphEntityResponse } from "../types/apiTypes";

interface GraphNode {
  id: string;
  type: string;
  val: number;
  color: string;
  riskScore: number;
}

interface GraphLink {
  source: string;
  target: string;
  amount: number;
  fraudScore: number;
}

interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
}

interface Props {
  entityIds: string[];
  onEntitySelect?: (entityId: string) => void;
}

function riskNodeColor(score: number): string {
  if (score >= 0.7) return "#EF4444"; // red — high risk
  if (score >= 0.4) return "#F59E0B"; // orange — medium risk
  return "#3B82F6"; // blue — normal
}

export default function GraphView({ entityIds, onEntitySelect }: Props) {
  const [graphData, setGraphData] = useState<GraphData>({
    nodes: [],
    links: [],
  });
  const [selected, setSelected] = useState<GraphEntityResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const nodeMapRef = useRef<Map<string, GraphNode>>(new Map());
  const linkSetRef = useRef<Set<string>>(new Set());

  const buildGraph = useCallback(async () => {
    if (entityIds.length === 0) return;
    setLoading(true);

    const nodeMap = new Map<string, GraphNode>();
    const links: GraphLink[] = [];
    const linkSet = new Set<string>();

    for (const eid of entityIds.slice(0, 20)) {
      try {
        const data = await getGraphEntity(eid);

        const avgFraud =
          data.neighbors.length > 0
            ? data.neighbors.reduce((s, n) => s + n.fraud_score, 0) /
              data.neighbors.length
            : 0;

        if (!nodeMap.has(eid)) {
          nodeMap.set(eid, {
            id: eid,
            type: data.entity_type,
            val: Math.max(4, data.degree_centrality * 30),
            color: riskNodeColor(avgFraud),
            riskScore: avgFraud,
          });
        }

        for (const nb of data.neighbors) {
          if (!nodeMap.has(nb.entity_id)) {
            nodeMap.set(nb.entity_id, {
              id: nb.entity_id,
              type: "entity",
              val: 4,
              color: riskNodeColor(nb.fraud_score),
              riskScore: nb.fraud_score,
            });
          }

          const linkKey =
            nb.direction === "outgoing"
              ? `${eid}->${nb.entity_id}`
              : `${nb.entity_id}->${eid}`;

          if (!linkSet.has(linkKey)) {
            linkSet.add(linkKey);
            if (nb.direction === "outgoing") {
              links.push({
                source: eid,
                target: nb.entity_id,
                amount: nb.transaction_amount,
                fraudScore: nb.fraud_score,
              });
            } else {
              links.push({
                source: nb.entity_id,
                target: eid,
                amount: nb.transaction_amount,
                fraudScore: nb.fraud_score,
              });
            }
          }
        }
      } catch {
        /* entity not in graph */
      }
    }

    nodeMapRef.current = nodeMap;
    linkSetRef.current = linkSet;
    setGraphData({ nodes: Array.from(nodeMap.values()), links });
    setLoading(false);
  }, [entityIds]);

  /* Expand neighbor nodes on demand */
  const expandNode = useCallback(
    async (nodeId: string) => {
      try {
        const data = await getGraphEntity(nodeId);
        const nodeMap = new Map(nodeMapRef.current);
        const links = [...graphData.links];
        const linkSet = new Set(linkSetRef.current);
        let added = false;

        for (const nb of data.neighbors) {
          if (!nodeMap.has(nb.entity_id)) {
            nodeMap.set(nb.entity_id, {
              id: nb.entity_id,
              type: "entity",
              val: 4,
              color: riskNodeColor(nb.fraud_score),
              riskScore: nb.fraud_score,
            });
            added = true;
          }

          const linkKey =
            nb.direction === "outgoing"
              ? `${nodeId}->${nb.entity_id}`
              : `${nb.entity_id}->${nodeId}`;

          if (!linkSet.has(linkKey)) {
            linkSet.add(linkKey);
            links.push(
              nb.direction === "outgoing"
                ? {
                    source: nodeId,
                    target: nb.entity_id,
                    amount: nb.transaction_amount,
                    fraudScore: nb.fraud_score,
                  }
                : {
                    source: nb.entity_id,
                    target: nodeId,
                    amount: nb.transaction_amount,
                    fraudScore: nb.fraud_score,
                  }
            );
            added = true;
          }
        }

        if (added) {
          nodeMapRef.current = nodeMap;
          linkSetRef.current = linkSet;
          setGraphData({ nodes: Array.from(nodeMap.values()), links });
        }
      } catch {
        /* ignore */
      }
    },
    [graphData.links]
  );

  useEffect(() => {
    buildGraph();
  }, [buildGraph]);

  if (entityIds.length === 0) {
    return (
      <div className="rounded-xl border border-gray-200 bg-white p-6">
        <h3 className="text-base font-semibold text-gray-800 mb-2">
          Transaction Network
        </h3>
        <p className="text-sm text-gray-400">
          Run the investigation pipeline to view the transaction network graph.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
      <div className="border-b border-gray-200 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <h3 className="text-base font-semibold text-gray-800">
            Transaction Network
            <span className="ml-2 text-sm font-normal text-gray-400">
              ({graphData.nodes.length} nodes, {graphData.links.length} edges)
            </span>
          </h3>
          {/* Risk color legend */}
          <div className="flex items-center gap-3 text-[10px] text-gray-500">
            <span className="flex items-center gap-1">
              <span className="inline-block h-2.5 w-2.5 rounded-full bg-red-500" />
              High
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block h-2.5 w-2.5 rounded-full bg-amber-500" />
              Medium
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block h-2.5 w-2.5 rounded-full bg-blue-500" />
              Normal
            </span>
          </div>
        </div>
        {/* Edge legend */}
        <div className="flex items-center gap-3 text-[10px] text-gray-400 px-6 pb-1">
          <span className="flex items-center gap-1">
            <span className="inline-block h-0.5 w-4 bg-red-700" />
            Shell / Round-trip
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block h-0.5 w-4 bg-purple-600" />
            Layering
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block h-0.5 w-4 bg-orange-600" />
            Structuring
          </span>
        </div>
        {loading && (
          <span className="text-xs text-blue-600 animate-pulse">Loading…</span>
        )}
      </div>

      <div ref={containerRef} className="h-[400px] bg-gray-50 relative">
        {graphData.nodes.length > 0 && (
          <ForceGraph2D
            graphData={graphData}
            width={containerRef.current?.clientWidth ?? 600}
            height={400}
            nodeLabel={() => ""}
            nodeColor={(n: GraphNode) => n.color}
            nodeVal={(n: GraphNode) => n.val}
            linkDirectionalArrowLength={4}
            linkDirectionalArrowRelPos={1}
            linkColor={(l: GraphLink) => {
              if (l.fraudScore >= 0.8) return "#DC2626CC"; // deep red — highest risk (round-tripping/shell)
              if (l.fraudScore >= 0.6) return "#9333EACC"; // purple — layering patterns
              if (l.fraudScore >= 0.5) return "#EA580CCC"; // orange — structuring patterns
              return "#CBD5E180"; // default gray
            }}
            linkWidth={(l: GraphLink) =>
              l.fraudScore >= 0.5
                ? Math.max(2, Math.min(5, l.amount / 8000))
                : Math.max(1, Math.min(3, l.amount / 10000))
            }
            linkLineDash={(l: GraphLink) =>
              l.fraudScore >= 0.8 ? [6, 3] : l.fraudScore >= 0.5 ? [4, 2] : null
            }
            onNodeClick={(node: GraphNode) => {
              expandNode(node.id);
              getGraphEntity(node.id)
                .then(setSelected)
                .catch(() => setSelected(null));
              onEntitySelect?.(node.id);
            }}
            onNodeHover={(node: GraphNode | null) => setHoveredNode(node)}
            backgroundColor="#F9FAFB"
          />
        )}

        {/* Hover tooltip */}
        {hoveredNode && (
          <div className="absolute top-3 right-3 z-10 bg-white border border-gray-200 rounded-lg shadow px-3 py-2 pointer-events-none">
            <p className="text-xs font-mono font-semibold text-gray-700">
              {hoveredNode.id}
            </p>
            <p className="text-xs text-gray-500 mt-0.5">
              Risk:{" "}
              <span
                className={`font-bold ${
                  hoveredNode.riskScore >= 0.7
                    ? "text-red-600"
                    : hoveredNode.riskScore >= 0.4
                    ? "text-amber-600"
                    : "text-blue-600"
                }`}
              >
                {(hoveredNode.riskScore * 100).toFixed(0)}%
              </span>
            </p>
          </div>
        )}
      </div>

      {/* Selected entity panel */}
      {selected && (
        <div className="border-t border-gray-200 bg-gray-50 px-6 py-4">
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-sm font-semibold text-gray-700">
              {selected.entity_id}
            </h4>
            <button
              onClick={() => setSelected(null)}
              className="text-xs text-gray-400 hover:text-gray-600"
            >
              Close
            </button>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 text-xs">
            <div className="bg-white rounded-lg p-2 border border-gray-200">
              <p className="text-gray-400">Degree</p>
              <p className="font-semibold text-gray-700">
                {selected.degree_centrality.toFixed(3)}
              </p>
            </div>
            <div className="bg-white rounded-lg p-2 border border-gray-200">
              <p className="text-gray-400">Betweenness</p>
              <p className="font-semibold text-gray-700">
                {selected.betweenness_centrality.toFixed(4)}
              </p>
            </div>
            <div className="bg-white rounded-lg p-2 border border-gray-200">
              <p className="text-gray-400">PageRank</p>
              <p className="font-semibold text-gray-700">
                {selected.pagerank.toFixed(4)}
              </p>
            </div>
            <div className="bg-white rounded-lg p-2 border border-gray-200">
              <p className="text-gray-400">In / Out</p>
              <p className="font-semibold text-gray-700">
                {selected.in_degree} / {selected.out_degree}
              </p>
            </div>
            <div className="bg-white rounded-lg p-2 border border-gray-200">
              <p className="text-gray-400">Community</p>
              <p className="font-semibold text-gray-700">
                {selected.community_id}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
