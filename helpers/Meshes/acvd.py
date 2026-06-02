from collections import deque
from dataclasses import dataclass
import heapq
import math

import adsk.core
import adsk.fusion

from ... import constants
from .. import Vectors
from . import core as meshCore
from . import remesh as meshRemesh
from . import topology


@dataclass
class AcvdSettings:
    """Store runtime-configurable parameters used by the ACVD tessellation pipeline.

    Attributes:
        surfaceTolerance: Source BRep tessellation tolerance forwarded to Fusion mesh generation.
        maxNormalDeviation: Source BRep tessellation angular deviation forwarded to Fusion.
        maxAspectRatio: Source BRep tessellation aspect-ratio limit forwarded to Fusion.
        subdivisionTargetRatio: Desired refined support-mesh density relative to final cluster count.
        maxSubdivisionIterations: Maximum number of support-mesh subdivision passes.
        maxClusteringIterations: Maximum number of ACVD energy-minimization iterations.
        minimumMovedFraction: Early-stop threshold for assignment changes between ACVD iterations.
        preserveOpenBoundaryEnabled: Preserve and constrain the open boundary when the selected region is open.
        edgeLengthEqualizationEnabled: Enable or disable the final optional edge equalization pass.
        edgeLengthEqualizationIterations: Number of iterations for the final equalization pass.
        edgeLengthEqualizationBlend: Blend factor used by the final equalization pass.
        midpointSurfaceCompensationEnabled: Enable or disable the midpoint-to-surface compensation pass.
        midpointSurfaceCompensationIterations: Number of iterations for the midpoint compensation pass.
        midpointSurfaceCompensationBlend: Blend factor used by the midpoint compensation pass.
    """

    surfaceTolerance: float
    maxNormalDeviation: float
    maxAspectRatio: float
    subdivisionTargetRatio: int
    maxSubdivisionIterations: int
    maxClusteringIterations: int
    minimumMovedFraction: float
    preserveOpenBoundaryEnabled: bool
    edgeLengthEqualizationEnabled: bool
    edgeLengthEqualizationIterations: int
    edgeLengthEqualizationBlend: float
    midpointSurfaceCompensationEnabled: bool = constants.MeshRemesh.surfaceCurvatureCompensationEnabled
    midpointSurfaceCompensationIterations: int = constants.MeshRemesh.acvdMidpointSurfaceCompensationIterations
    midpointSurfaceCompensationBlend: float = constants.MeshRemesh.acvdMidpointSurfaceCompensationBlend

    @classmethod
    def fromDefaults(cls) -> 'AcvdSettings':
        """Build a settings object from the current default constants."""
        return cls(
            constants.MeshRemesh.surfaceTolerance,
            constants.MeshRemesh.maxNormalDeviation,
            constants.MeshRemesh.maxAspectRatio,
            constants.MeshRemesh.acvdSubdivisionTargetRatio,
            constants.MeshRemesh.acvdMaxSubdivisionIterations,
            constants.MeshRemesh.acvdMaxClusteringIterations,
            constants.MeshRemesh.acvdMinimumMovedFraction,
            constants.MeshRemesh.acvdPreserveOpenBoundaryEnabled,
            constants.MeshRemesh.acvdEdgeLengthEqualizationEnabled,
            constants.MeshRemesh.acvdEdgeLengthEqualizationIterations,
            constants.MeshRemesh.acvdEdgeLengthEqualizationBlend,
            constants.MeshRemesh.surfaceCurvatureCompensationEnabled,
            constants.MeshRemesh.acvdMidpointSurfaceCompensationIterations,
            constants.MeshRemesh.acvdMidpointSurfaceCompensationBlend
        )


@dataclass
class AcvdTessellationResult:
    """Store the final mesh produced by ACVD together with preview metadata.

    Attributes:
        finalMeshData: Flat triangle mesh data ready for downstream consumers.
        clusterNormals: One normal per logical ACVD vertex before unused vertices are removed.
        usedClusterIndices: Mapping from the compacted final mesh vertices back to ACVD cluster indices.
    """

    finalMeshData: meshCore.TriangleMeshData
    clusterNormals: list[adsk.core.Vector3D]
    usedClusterIndices: list[int]


@dataclass
class AcvdClusteringData:
    """Collect all intermediate results needed to build the final ACVD mesh.

    Attributes:
        refinedPoints: Support-mesh vertices used during clustering.
        refinedTriangles: Support-mesh triangles used during clustering.
        pointAreas: Per-vertex accumulated triangle areas on the support mesh.
        assignments: Cluster assignment for every support-mesh vertex.
        seeds: Vertex index used as representative for each cluster.
        centroids: Area-weighted centroid for each cluster.
        boundaryClusterIndices: Clusters that touch the open boundary and must preserve it.
        protectedBoundaryClusterIndices: Boundary clusters pinned to exact source BRep corner vertices.
        protectedBoundaryPointsByVertexIndex: Exact source BRep boundary points keyed by refined vertex index.
    """

    refinedPoints: list[adsk.core.Point3D]
    refinedTriangles: list[meshCore.TriangleIndices]
    pointAreas: list[float]
    assignments: list[int]
    seeds: list[int]
    centroids: list[adsk.core.Point3D]
    boundaryClusterIndices: set[int]
    protectedBoundaryClusterIndices: set[int]
    protectedBoundaryPointsByVertexIndex: dict[int, adsk.core.Point3D]


@dataclass
class AcvdMeshContext:
    """Store the shared support-mesh data used by the ACVD clustering pipeline.

    Attributes:
        refinedPoints: Refined vertices used as the domain for clustering.
        refinedTriangles: Refined triangles used as the domain for clustering.
        edges: Unique refined-mesh edges used by energy minimization.
        pointAreas: Per-vertex accumulated area values.
        neighbors: Vertex adjacency graph of the refined mesh.
        totalArea: Total area used to estimate target cluster count.
        boundaryVertexIndices: Refined vertices that lie on the preserved open boundary.
        protectedBoundaryVertexIndices: Boundary vertices that match original BRep boundary vertices.
        protectedBoundaryPointsByVertexIndex: Exact source BRep boundary points keyed by refined vertex index.
        boundarySeedIndices: Seed vertices sampled along the preserved boundary before interior seeding.
    """

    refinedPoints: list[adsk.core.Point3D]
    refinedTriangles: list[meshCore.TriangleIndices]
    edges: list[tuple[int, int]]
    pointAreas: list[float]
    neighbors: dict[int, set[int]]
    totalArea: float
    boundaryVertexIndices: set[int]
    protectedBoundaryVertexIndices: set[int]
    protectedBoundaryPointsByVertexIndex: dict[int, adsk.core.Point3D]
    boundarySeedIndices: list[int]


@dataclass
class AcvdClusterState:
    """Store accumulated isotropic ACVD energy data for one cluster."""

    sumX: float
    sumY: float
    sumZ: float
    totalWeight: float
    energy: float


def createAcvdTessellationResult(
    faces: list[adsk.fusion.BRepFace],
    accuracy: float,
    settings: AcvdSettings | None = None
) -> AcvdTessellationResult | None:
    """Run the full ACVD pipeline and return mesh plus preview metadata.

    This is the main public entry point used by preview and pave-related flows.
    It builds the clustering support data first and then converts it into the final
    compact mesh representation.

    Args:
        faces: Selected Fusion faces that should be tessellated together.
        accuracy: Requested edge length target in internal Fusion units.

    Returns:
        Fully built ACVD tessellation result, or None when meshing/clustering fails.
    """
    effectiveSettings = settings or AcvdSettings.fromDefaults()
    clusteringData = _buildAcvdClusteringData(faces, accuracy, effectiveSettings)
    if clusteringData is None:
        return None

    return buildAcvdTessellationResult(clusteringData, faces, effectiveSettings)


def tessellateFaces(
    faces: list[adsk.fusion.BRepFace],
    accuracy: float,
    settings: AcvdSettings | None = None
) -> meshCore.TriangleMeshData | None:
    """Run the ACVD pipeline and return only the final mesh data.

    This helper exists for call sites that only need triangles and do not need
    normals or cluster index mapping.

    Args:
        faces: Selected Fusion faces that should be tessellated together.
        accuracy: Requested edge length target in internal Fusion units.

    Returns:
        Flat triangle mesh data, or None when the ACVD build cannot complete.
    """
    effectiveSettings = settings or AcvdSettings.fromDefaults()
    clusteringData = _buildAcvdClusteringData(faces, accuracy, effectiveSettings)
    if clusteringData is None:
        return None

    finalMeshData, _ = _buildFinalMeshData(clusteringData, faces, effectiveSettings)
    return finalMeshData


def buildAcvdTessellationResult(
    clusteringData: AcvdClusteringData,
    faces: list[adsk.fusion.BRepFace] | None = None,
    settings: AcvdSettings | None = None
) -> AcvdTessellationResult:
    """Convert precomputed clustering data into the final ACVD result object.

    Args:
        clusteringData: Intermediate data produced by the clustering stage.
        faces: Optional source faces used to project generated vertices back to the surface.

    Returns:
        Final ACVD result containing mesh data, normals, and compacted vertex mapping.
    """
    effectiveSettings = settings or AcvdSettings.fromDefaults()
    clusterCount = len(clusteringData.seeds)
    clusterNormals = computeClusterNormals(
        clusteringData.refinedPoints,
        clusteringData.refinedTriangles,
        clusteringData.pointAreas,
        clusteringData.assignments,
        clusterCount
    )
    finalMeshData, usedClusterIndices = _buildFinalMeshData(clusteringData, faces, effectiveSettings)

    return AcvdTessellationResult(
        finalMeshData,
        clusterNormals,
        usedClusterIndices
    )


def _buildAcvdClusteringData(
    faces: list[adsk.fusion.BRepFace],
    accuracy: float,
    settings: AcvdSettings | None = None
) -> AcvdClusteringData | None:
    """Build the complete ACVD clustering state before final mesh extraction.

    The function creates a refined support mesh, estimates the desired number of
    clusters, seeds boundary and interior samples, and then improves the initial
    clustering with ACVD-style local energy minimization and connectivity cleanup.

    Args:
        faces: Selected Fusion faces that define the meshing domain.
        accuracy: Requested target edge length in internal Fusion units.

    Returns:
        Clustering data that can be converted into final mesh outputs, or None if
        the support mesh cannot be constructed.
    """
    effectiveSettings = settings or AcvdSettings.fromDefaults()
    meshContext = createAcvdMeshContext(faces, accuracy, accuracy, effectiveSettings)
    if meshContext is None:
        return None

    targetClusterCount = getTargetClusterCount(meshContext.totalArea, accuracy)
    targetClusterCount = max(targetClusterCount, len(meshContext.boundarySeedIndices))
    clusterCount = min(targetClusterCount, len(meshContext.refinedPoints))
    seeds = initializeSeeds(
        meshContext.refinedPoints,
        meshContext.pointAreas,
        clusterCount,
        meshContext.boundarySeedIndices
    )
    if not seeds:
        return None

    clusterCount = len(seeds)
    boundarySeedClusterIndices = {
        clusterIndex
        for clusterIndex, seedIndex in enumerate(seeds)
        if seedIndex in meshContext.boundaryVertexIndices
    }
    lockedClusterIndices = {
        clusterIndex
        for clusterIndex, seedIndex in enumerate(seeds)
        if seedIndex in meshContext.protectedBoundaryVertexIndices
    }
    assignments = initializeClustersFromSeeds(
        meshContext.refinedPoints,
        meshContext.pointAreas,
        meshContext.neighbors,
        seeds,
        meshContext.boundaryVertexIndices,
        boundarySeedClusterIndices
    )
    assignments = minimizeAssignmentsEnergy(
        meshContext.refinedPoints,
        meshContext.pointAreas,
        assignments,
        clusterCount,
        meshContext.edges,
        meshContext.neighbors,
        meshContext.boundaryVertexIndices,
        meshContext.protectedBoundaryVertexIndices,
        boundarySeedClusterIndices,
        effectiveSettings.maxClusteringIterations,
        effectiveSettings.minimumMovedFraction
    )

    for _ in range(2):
        disconnectedClusterCount = cleanDisconnectedClusters(
            assignments,
            clusterCount,
            meshContext.neighbors,
            meshContext.protectedBoundaryVertexIndices
        )
        unassignedCount = growUnassignedVertices(
            meshContext.refinedPoints,
            meshContext.pointAreas,
            assignments,
            clusterCount,
            meshContext.neighbors,
            meshContext.boundaryVertexIndices,
            boundarySeedClusterIndices
        )
        if disconnectedClusterCount == 0 and unassignedCount == 0:
            break

        assignments = minimizeAssignmentsEnergy(
            meshContext.refinedPoints,
            meshContext.pointAreas,
            assignments,
            clusterCount,
            meshContext.edges,
            meshContext.neighbors,
            meshContext.boundaryVertexIndices,
            meshContext.protectedBoundaryVertexIndices,
            boundarySeedClusterIndices,
            effectiveSettings.maxClusteringIterations,
            effectiveSettings.minimumMovedFraction
        )

    centroids = computeCentroids(
        meshContext.refinedPoints,
        meshContext.pointAreas,
        assignments,
        clusterCount
    )
    seeds = updateSeeds(
        meshContext.refinedPoints,
        assignments,
        centroids,
        seeds,
        clusterCount,
        meshContext.boundaryVertexIndices,
        boundarySeedClusterIndices,
        lockedClusterIndices
    )
    boundaryClusterIndices = {
        assignments[pointIndex]
        for pointIndex in meshContext.boundaryVertexIndices
        if 0 <= assignments[pointIndex] < clusterCount
    }
    protectedBoundaryClusterIndices = {
        clusterIndex
        for clusterIndex, seedIndex in enumerate(seeds)
        if seedIndex in meshContext.protectedBoundaryPointsByVertexIndex
    }

    return AcvdClusteringData(
        meshContext.refinedPoints,
        meshContext.refinedTriangles,
        meshContext.pointAreas,
        assignments,
        seeds,
        centroids,
        boundaryClusterIndices,
        protectedBoundaryClusterIndices,
        meshContext.protectedBoundaryPointsByVertexIndex
    )


def createAcvdMeshContext(
    faces: list[adsk.fusion.BRepFace],
    accuracy: float,
    boundarySeedSpacing: float,
    settings: AcvdSettings
) -> AcvdMeshContext | None:
    """Create the refined support mesh and all metadata used by ACVD clustering.

    The support mesh is built from the selected faces, subdivided until it is dense
    enough for stable clustering, and then annotated with area, adjacency, and
    boundary information.

    Args:
        faces: Selected Fusion faces that define the meshing domain.
        accuracy: Requested target edge length in internal Fusion units.
        boundarySeedSpacing: Desired spacing between boundary seeds.

    Returns:
        Support-mesh context, or None if the faces cannot be meshed.
    """
    meshResult = topology.meshFaces(
        faces,
        accuracy,
        settings.surfaceTolerance,
        settings.maxNormalDeviation,
        settings.maxAspectRatio
    )
    if meshResult is None:
        return None

    sourcePoints, sourceTriangles = meshResult
    _, totalArea = meshCore.buildPointAreas(sourcePoints, sourceTriangles)
    if totalArea <= constants.MeshRemesh.acvdMinTriangleArea:
        totalArea = sum(face.area for face in faces)

    targetClusterCount = getTargetClusterCount(totalArea, accuracy)
    refinedPoints = sourcePoints
    refinedTriangles = sourceTriangles
    targetPointCount = targetClusterCount * settings.subdivisionTargetRatio

    for _ in range(settings.maxSubdivisionIterations):
        if len(refinedPoints) >= targetPointCount:
            break

        previousPointCount = len(refinedPoints)
        refinedPoints, refinedTriangles = meshCore.subdivideTriangleMesh(refinedPoints, refinedTriangles)
        refinedPoints = projectMeshPointsToFaces(refinedPoints, faces, previousPointCount)

    pointAreas, _ = meshCore.buildPointAreas(refinedPoints, refinedTriangles)
    edges = meshCore.buildUniqueEdges(refinedTriangles)
    neighbors = meshCore.buildVertexNeighbors(refinedTriangles)
    boundaryVertexIndices: set[int] = set()
    protectedBoundaryVertexIndices: set[int] = set()
    protectedBoundaryPointsByVertexIndex: dict[int, adsk.core.Point3D] = {}
    boundarySeedIndices: list[int] = []

    if settings.preserveOpenBoundaryEnabled:
        sourceBoundaryVertexPoints = topology.getBoundaryVertexPointsFromFaces(faces)
        refinedBoundaryEdges = topology.getBoundaryEdges(refinedTriangles)
        boundaryVertexIndices = {vertexIndex for edge in refinedBoundaryEdges for vertexIndex in edge}
        protectedBoundaryPointsByVertexIndex = topology.getMatchedTargetPointsByVertexIndex(
            refinedPoints,
            sourceBoundaryVertexPoints,
            constants.MeshRemesh.acvdMinimumSamplingDistanceCm
        )
        protectedBoundaryVertexIndices = {
            vertexIndex
            for vertexIndex in protectedBoundaryPointsByVertexIndex
            if vertexIndex in boundaryVertexIndices
        }
        protectedBoundaryPointsByVertexIndex = {
            vertexIndex: point
            for vertexIndex, point in protectedBoundaryPointsByVertexIndex.items()
            if vertexIndex in protectedBoundaryVertexIndices
        }
        boundarySeedIndices = topology.getBoundarySeedIndices(
            refinedPoints,
            refinedTriangles,
            boundarySeedSpacing,
            protectedBoundaryVertexIndices
        )

    return AcvdMeshContext(
        refinedPoints,
        refinedTriangles,
        edges,
        pointAreas,
        neighbors,
        totalArea,
        boundaryVertexIndices,
        protectedBoundaryVertexIndices,
        protectedBoundaryPointsByVertexIndex,
        boundarySeedIndices
    )


def _buildFinalMeshData(
    clusteringData: AcvdClusteringData,
    faces: list[adsk.fusion.BRepFace] | None = None,
    settings: AcvdSettings | None = None
) -> tuple[meshCore.TriangleMeshData, list[int]]:
    """Create the compact final mesh from the ACVD clustering state.

    This stage builds one point per cluster, collapses the support triangles into
    cluster triangles, optionally smooths the resulting vertices to even out local
    edge lengths, and then removes any vertices not referenced by the final mesh.

    Args:
        clusteringData: Result of the ACVD clustering stage.
        faces: Optional source faces used to keep vertices on the original surface.

    Returns:
        Tuple of compact flat mesh data and mapping to original cluster indices.
    """
    effectiveSettings = settings or AcvdSettings.fromDefaults()
    clusterCount = len(clusteringData.seeds)
    clusterPoints: list[adsk.core.Point3D] = []

    for clusterIndex in range(clusterCount):
        seedIndex = clusteringData.seeds[clusterIndex]

        if clusterIndex in clusteringData.protectedBoundaryClusterIndices:
            protectedBoundaryPoint = clusteringData.protectedBoundaryPointsByVertexIndex.get(seedIndex)
            if protectedBoundaryPoint is not None:
                clusterPoints.append(protectedBoundaryPoint.copy())
                continue

        if clusterIndex in clusteringData.boundaryClusterIndices and 0 <= seedIndex < len(clusteringData.refinedPoints):
            clusterPoints.append(getSnappedPointOrCopy(faces, clusteringData.refinedPoints[seedIndex]))
            continue

        if clusterIndex < len(clusteringData.centroids):
            centroid = clusteringData.centroids[clusterIndex]
            clusterPoints.append(getSnappedPointOrCopy(faces, centroid))
            continue

        if 0 <= seedIndex < len(clusteringData.refinedPoints):
            clusterPoints.append(getSnappedPointOrCopy(faces, clusteringData.refinedPoints[seedIndex]))
            continue

        clusterPoints.append(getSnappedPointOrCopy(faces, adsk.core.Point3D.create(0.0, 0.0, 0.0)))

    finalTriangles = buildRemeshedTriangles(
        clusteringData.refinedPoints,
        clusteringData.refinedTriangles,
        clusteringData.assignments,
        clusterPoints
    )
    finalTriangles = addMissingProtectedBoundaryTriangles(
        clusteringData.refinedPoints,
        clusteringData.refinedTriangles,
        clusteringData.assignments,
        clusterPoints,
        finalTriangles,
        clusteringData.protectedBoundaryClusterIndices
    )
    if not finalTriangles:
        return topology.toFlatMeshData(clusteringData.refinedPoints, clusteringData.refinedTriangles), list(range(clusterCount))

    if effectiveSettings.edgeLengthEqualizationEnabled:
        clusterPoints = equalizeClusterEdgeLengths(
            clusterPoints,
            finalTriangles,
            faces,
            clusteringData.boundaryClusterIndices,
            effectiveSettings.edgeLengthEqualizationIterations,
            effectiveSettings.edgeLengthEqualizationBlend
        )

    usedClusterIndices = sorted({clusterIndex for triangle in finalTriangles for clusterIndex in triangle})
    clusterIndexMap = {
        clusterIndex: mappedIndex
        for mappedIndex, clusterIndex in enumerate(usedClusterIndices)
    }
    finalPoints = [getSnappedPointOrCopy(faces, clusterPoints[clusterIndex]) for clusterIndex in usedClusterIndices]
    remappedTriangles = [
        (clusterIndexMap[index0], clusterIndexMap[index1], clusterIndexMap[index2])
        for index0, index1, index2 in finalTriangles
    ]
    lockedFinalVertexIndices = {
        clusterIndexMap[clusterIndex]
        for clusterIndex in usedClusterIndices
        if clusterIndex in clusteringData.boundaryClusterIndices
    }
    applyProtectedBoundaryPoints(
        finalPoints,
        usedClusterIndices,
        clusteringData.seeds,
        clusteringData.protectedBoundaryClusterIndices,
        clusteringData.protectedBoundaryPointsByVertexIndex
    )

    if effectiveSettings.midpointSurfaceCompensationEnabled:
        finalPoints = compensatePointsForSurfaceCurvature(
            finalPoints,
            remappedTriangles,
            faces,
            lockedFinalVertexIndices,
            effectiveSettings.midpointSurfaceCompensationIterations,
            effectiveSettings.midpointSurfaceCompensationBlend
        )
        applyProtectedBoundaryPoints(
            finalPoints,
            usedClusterIndices,
            clusteringData.seeds,
            clusteringData.protectedBoundaryClusterIndices,
            clusteringData.protectedBoundaryPointsByVertexIndex
        )

    return topology.toFlatMeshData(finalPoints, remappedTriangles), usedClusterIndices


def applyProtectedBoundaryPoints(
    points: list[adsk.core.Point3D],
    usedClusterIndices: list[int],
    seeds: list[int],
    protectedBoundaryClusterIndices: set[int],
    protectedBoundaryPointsByVertexIndex: dict[int, adsk.core.Point3D]
) -> None:
    """Restore exact source boundary corner points for protected final vertices."""
    if not points or not usedClusterIndices or not protectedBoundaryClusterIndices or not protectedBoundaryPointsByVertexIndex:
        return

    clusterIndexMap = {
        clusterIndex: mappedIndex
        for mappedIndex, clusterIndex in enumerate(usedClusterIndices)
    }

    for clusterIndex in protectedBoundaryClusterIndices:
        mappedIndex = clusterIndexMap.get(clusterIndex)
        if mappedIndex is None or mappedIndex >= len(points) or clusterIndex >= len(seeds):
            continue

        protectedBoundaryPoint = protectedBoundaryPointsByVertexIndex.get(seeds[clusterIndex])
        if protectedBoundaryPoint is None:
            continue

        points[mappedIndex] = protectedBoundaryPoint.copy()


def buildRemeshedTriangles(
    points: list[adsk.core.Point3D],
    triangles: list[meshCore.TriangleIndices],
    assignments: list[int],
    clusterPoints: list[adsk.core.Point3D]
) -> list[meshCore.TriangleIndices]:
    """Collapse support-mesh triangles into triangles between ACVD cluster vertices.

    The function aggregates source triangle orientations per unique cluster triplet,
    which allows the final triangle winding to remain consistent after the collapse.

    Args:
        points: Support-mesh vertices.
        triangles: Support-mesh triangles.
        assignments: Cluster assignment for every support-mesh vertex.
        clusterPoints: One representative point per cluster.

    Returns:
        Triangle list expressed in cluster indices.
    """
    accumulatedNormals: dict[tuple[int, int, int], adsk.core.Vector3D] = {}

    for index0, index1, index2 in triangles:
        cluster0 = assignments[index0]
        cluster1 = assignments[index1]
        cluster2 = assignments[index2]
        if len({cluster0, cluster1, cluster2}) < 3:
            continue

        faceKey = tuple(sorted((cluster0, cluster1, cluster2)))
        triangleNormal = points[index0].vectorTo(points[index1]).crossProduct(
            points[index0].vectorTo(points[index2])
        )
        accumulatedNormals.setdefault(faceKey, adsk.core.Vector3D.create(0.0, 0.0, 0.0)).add(triangleNormal)

    remeshedTriangles: list[meshCore.TriangleIndices] = []

    for clusterIndices, normalSum in accumulatedNormals.items():
        cluster0, cluster1, cluster2 = clusterIndices
        faceNormal = clusterPoints[cluster0].vectorTo(clusterPoints[cluster1]).crossProduct(
            clusterPoints[cluster0].vectorTo(clusterPoints[cluster2])
        )
        if faceNormal.length <= constants.MeshRemesh.acvdMinTriangleArea:
            continue

        if faceNormal.dotProduct(normalSum) < 0.0:
            remeshedTriangles.append((cluster0, cluster2, cluster1))
        else:
            remeshedTriangles.append((cluster0, cluster1, cluster2))

    return remeshedTriangles


def addMissingProtectedBoundaryTriangles(
    points: list[adsk.core.Point3D],
    triangles: list[meshCore.TriangleIndices],
    assignments: list[int],
    clusterPoints: list[adsk.core.Point3D],
    finalTriangles: list[meshCore.TriangleIndices],
    protectedBoundaryClusterIndices: set[int]
) -> list[meshCore.TriangleIndices]:
    """Guarantee that protected boundary corner clusters remain part of the final mesh."""
    if not protectedBoundaryClusterIndices:
        return finalTriangles

    usedClusterIndices = {clusterIndex for triangle in finalTriangles for clusterIndex in triangle}
    missingProtectedClusterIndices = sorted(protectedBoundaryClusterIndices - usedClusterIndices)
    if not missingProtectedClusterIndices:
        return finalTriangles

    clusterAdjacency = buildClusterAdjacency(assignments, triangles)
    boundaryClusterAdjacency = buildBoundaryClusterAdjacency(assignments, topology.getBoundaryEdges(triangles))
    clusterSupportNormals = buildClusterSupportNormals(points, triangles, assignments)
    clusterTripletSupport = buildClusterTripletSupport(assignments, triangles)
    augmentedTriangles = finalTriangles[:]
    existingTriangleKeys = {tuple(sorted(triangle)) for triangle in augmentedTriangles}

    for clusterIndex in missingProtectedClusterIndices:
        orderedBoundaryNeighborIndices = sorted(
            boundaryClusterAdjacency.get(clusterIndex, set()),
            key=lambda neighborIndex: _distanceSquared(clusterPoints[clusterIndex], clusterPoints[neighborIndex])
        )
        orderedAdjacentClusterIndices = sorted(
            clusterAdjacency.get(clusterIndex, set()),
            key=lambda neighborIndex: _distanceSquared(clusterPoints[clusterIndex], clusterPoints[neighborIndex])
        )
        supportedTriplets = sorted(
            clusterTripletSupport.get(clusterIndex, {}).items(),
            key=lambda tripletData: (
                sum(neighborIndex in usedClusterIndices for neighborIndex in tripletData[0] if neighborIndex != clusterIndex),
                sum(neighborIndex in boundaryClusterAdjacency.get(clusterIndex, set()) for neighborIndex in tripletData[0] if neighborIndex != clusterIndex),
                tripletData[1],
                -sum(
                    _distanceSquared(clusterPoints[clusterIndex], clusterPoints[neighborIndex])
                    for neighborIndex in tripletData[0]
                    if neighborIndex != clusterIndex
                )
            ),
            reverse=True
        )
        candidateTrianglePairs: list[tuple[int, int]] = []

        for triplet, _ in supportedTriplets:
            triangleKey = tuple(sorted(triplet))
            if triangleKey in existingTriangleKeys:
                continue

            firstNeighborIndex, secondNeighborIndex = [
                neighborIndex
                for neighborIndex in triplet
                if neighborIndex != clusterIndex
            ]
            orientedTriangle = orientClusterTriangle(
                clusterIndex,
                firstNeighborIndex,
                secondNeighborIndex,
                clusterPoints,
                clusterSupportNormals.get(clusterIndex)
            )
            if orientedTriangle is None:
                continue

            augmentedTriangles.append(orientedTriangle)
            existingTriangleKeys.add(triangleKey)
            break

        if clusterIndex in {clusterIndex for triangle in augmentedTriangles for clusterIndex in triangle}:
            continue

        if len(orderedBoundaryNeighborIndices) >= 2:
            candidateTrianglePairs.append((orderedBoundaryNeighborIndices[0], orderedBoundaryNeighborIndices[1]))

        if len(orderedBoundaryNeighborIndices) >= 1:
            extraNeighborIndex = next(
                (
                    neighborIndex
                    for neighborIndex in orderedAdjacentClusterIndices
                    if neighborIndex != orderedBoundaryNeighborIndices[0]
                ),
                None
            )
            if extraNeighborIndex is not None:
                candidateTrianglePairs.append((orderedBoundaryNeighborIndices[0], extraNeighborIndex))

        if len(orderedAdjacentClusterIndices) >= 2:
            candidateTrianglePairs.append((orderedAdjacentClusterIndices[0], orderedAdjacentClusterIndices[1]))

        for firstPosition, firstNeighborIndex in enumerate(orderedAdjacentClusterIndices[:4]):
            for secondNeighborIndex in orderedAdjacentClusterIndices[firstPosition + 1:4]:
                candidateTrianglePairs.append((firstNeighborIndex, secondNeighborIndex))

        for firstNeighborIndex, secondNeighborIndex in candidateTrianglePairs:
            triangleKey = tuple(sorted((clusterIndex, firstNeighborIndex, secondNeighborIndex)))
            if len(triangleKey) < 3 or triangleKey in existingTriangleKeys:
                continue

            orientedTriangle = orientClusterTriangle(
                clusterIndex,
                firstNeighborIndex,
                secondNeighborIndex,
                clusterPoints,
                clusterSupportNormals.get(clusterIndex)
            )
            if orientedTriangle is None:
                continue

            augmentedTriangles.append(orientedTriangle)

            existingTriangleKeys.add(triangleKey)
            break

    return augmentedTriangles


def buildClusterTripletSupport(
    assignments: list[int],
    triangles: list[meshCore.TriangleIndices]
) -> dict[int, dict[tuple[int, int, int], int]]:
    """Count original support-mesh cluster triplets for each participating cluster."""
    clusterTripletSupport: dict[int, dict[tuple[int, int, int], int]] = {}

    for index0, index1, index2 in triangles:
        triplet = tuple(sorted({assignments[index0], assignments[index1], assignments[index2]}))
        if len(triplet) != 3 or triplet[0] < 0:
            continue

        for clusterIndex in triplet:
            clusterTripletSupport.setdefault(clusterIndex, {})[triplet] = (
                clusterTripletSupport.setdefault(clusterIndex, {}).get(triplet, 0) + 1
            )

    return clusterTripletSupport


def orientClusterTriangle(
    clusterIndex: int,
    firstNeighborIndex: int,
    secondNeighborIndex: int,
    clusterPoints: list[adsk.core.Point3D],
    supportNormal: adsk.core.Vector3D | None
) -> meshCore.TriangleIndices | None:
    """Build a consistently oriented cluster triangle or return None for degenerate input."""
    faceNormal = clusterPoints[clusterIndex].vectorTo(clusterPoints[firstNeighborIndex]).crossProduct(
        clusterPoints[clusterIndex].vectorTo(clusterPoints[secondNeighborIndex])
    )
    if faceNormal.length <= constants.MeshRemesh.acvdMinTriangleArea:
        return None

    if supportNormal is not None and supportNormal.length > constants.MeshRemesh.acvdMinTriangleArea:
        if faceNormal.dotProduct(supportNormal) < 0.0:
            return clusterIndex, secondNeighborIndex, firstNeighborIndex

    return clusterIndex, firstNeighborIndex, secondNeighborIndex


def buildClusterAdjacency(
    assignments: list[int],
    triangles: list[meshCore.TriangleIndices]
) -> dict[int, set[int]]:
    """Build cluster adjacency from support-mesh triangle connectivity."""
    clusterAdjacency: dict[int, set[int]] = {}

    for index0, index1, index2 in triangles:
        triangleClusterIndices = [assignments[index0], assignments[index1], assignments[index2]]
        uniqueClusterIndices = [clusterIndex for clusterIndex in sorted(set(triangleClusterIndices)) if clusterIndex >= 0]
        for clusterIndex in uniqueClusterIndices:
            clusterAdjacency.setdefault(clusterIndex, set())

        for startPosition, startClusterIndex in enumerate(uniqueClusterIndices):
            for endClusterIndex in uniqueClusterIndices[startPosition + 1:]:
                clusterAdjacency[startClusterIndex].add(endClusterIndex)
                clusterAdjacency[endClusterIndex].add(startClusterIndex)

    return clusterAdjacency


def buildBoundaryClusterAdjacency(
    assignments: list[int],
    boundaryEdges: list[tuple[int, int]]
) -> dict[int, set[int]]:
    """Build cluster adjacency only along the open boundary."""
    boundaryClusterAdjacency: dict[int, set[int]] = {}

    for startIndex, endIndex in boundaryEdges:
        startClusterIndex = assignments[startIndex]
        endClusterIndex = assignments[endIndex]
        if startClusterIndex < 0 or endClusterIndex < 0 or startClusterIndex == endClusterIndex:
            continue

        boundaryClusterAdjacency.setdefault(startClusterIndex, set()).add(endClusterIndex)
        boundaryClusterAdjacency.setdefault(endClusterIndex, set()).add(startClusterIndex)

    return boundaryClusterAdjacency


def buildClusterSupportNormals(
    points: list[adsk.core.Point3D],
    triangles: list[meshCore.TriangleIndices],
    assignments: list[int]
) -> dict[int, adsk.core.Vector3D]:
    """Accumulate source-mesh normals for each cluster to orient synthetic corner triangles."""
    clusterNormals: dict[int, adsk.core.Vector3D] = {}

    for index0, index1, index2 in triangles:
        triangleNormal = points[index0].vectorTo(points[index1]).crossProduct(
            points[index0].vectorTo(points[index2])
        )
        if triangleNormal.length <= constants.MeshRemesh.acvdMinTriangleArea:
            continue

        for clusterIndex in {assignments[index0], assignments[index1], assignments[index2]}:
            if clusterIndex < 0:
                continue

            clusterNormals.setdefault(clusterIndex, adsk.core.Vector3D.create(0.0, 0.0, 0.0)).add(triangleNormal)

    return clusterNormals


def equalizeClusterEdgeLengths(
    points: list[adsk.core.Point3D],
    triangles: list[meshCore.TriangleIndices],
    faces: list[adsk.fusion.BRepFace] | None,
    lockedVertexIndices: set[int],
    iterationCount: int,
    blendFactor: float
) -> list[adsk.core.Point3D]:
    """Relax cluster vertices using the average vector to adjacent vertices.

    The method works on the already collapsed ACVD mesh. For each non-locked vertex,
    it builds vectors to all adjacent vertices, averages them, moves the vertex by
    that average scaled by the requested blend factor, and then projects the point
    back to the source faces on every iteration for every processed vertex.

    Args:
        points: Cluster representative points before compaction.
        triangles: Triangles expressed in cluster indices.
        faces: Optional source faces used for surface projection after each move.
        lockedVertexIndices: Vertices that must remain fixed, usually boundary vertices.
        iterationCount: Number of relaxation iterations to perform.
        blendFactor: Blend between current and target position for stability.

    Returns:
        New list of relaxed points with the same indexing as the input list.
    """
    if iterationCount <= 0 or blendFactor <= 0.0 or not points or not triangles:
        return [point.copy() for point in points]

    vertexNeighbors = meshCore.buildVertexNeighbors(triangles)
    relaxedPoints = [point.copy() for point in points]
    clampedBlendFactor = max(0.0, min(1.0, blendFactor))

    for _ in range(iterationCount):
        nextPoints = [point.copy() for point in relaxedPoints]

        for pointIndex, point in enumerate(relaxedPoints):
            if pointIndex in lockedVertexIndices:
                continue

            candidatePoint = point.copy()
            neighborIndices = sorted(vertexNeighbors.get(pointIndex, set()))
            if len(neighborIndices) >= 2:
                neighborVectors = [
                    point.vectorTo(relaxedPoints[neighborIndex])
                    for neighborIndex in neighborIndices
                ]
                averageVector = Vectors.averageVector(neighborVectors)
                if averageVector is not None and averageVector.length > constants.MeshRemesh.acvdMinTriangleArea:
                    averageVector.scaleBy(clampedBlendFactor)
                    candidatePoint = adsk.core.Point3D.create(
                        point.x + averageVector.x,
                        point.y + averageVector.y,
                        point.z + averageVector.z
                    )

            projectedPoint = _projectPointToFaces(faces, candidatePoint)
            nextPoints[pointIndex] = projectedPoint if projectedPoint is not None else candidatePoint

        relaxedPoints = nextPoints

    return relaxedPoints


def compensatePointsForSurfaceCurvature(
    points: list[adsk.core.Point3D],
    triangles: list[meshCore.TriangleIndices],
    faces: list[adsk.fusion.BRepFace] | None,
    lockedVertexIndices: set[int],
    iterationCount: int,
    blendFactor: float
) -> list[adsk.core.Point3D]:
    """Offset final vertices along face normals so edge midpoints better fit the surface."""
    return meshRemesh.compensatePointsForSurfaceCurvature(
        points,
        triangles,
        faces,
        lockedVertexIndices,
        iterationCount,
        blendFactor
    )


def computeClusterNormals(
    points: list[adsk.core.Point3D],
    triangles: list[meshCore.TriangleIndices],
    pointAreas: list[float],
    assignments: list[int],
    clusterCount: int
) -> list[adsk.core.Vector3D]:
    """Compute one averaged normal for every ACVD cluster.

    Normals are first accumulated per support-mesh vertex and are then combined
    using area weights according to cluster membership.

    Args:
        points: Support-mesh vertices.
        triangles: Support-mesh triangles.
        pointAreas: Per-vertex accumulated areas.
        assignments: Cluster assignment for every support-mesh vertex.
        clusterCount: Number of clusters currently in use.

    Returns:
        Normalized normal vector for each cluster.
    """
    vertexNormals = [adsk.core.Vector3D.create(0.0, 0.0, 0.0) for _ in points]

    for index0, index1, index2 in triangles:
        triangleNormal = points[index0].vectorTo(points[index1]).crossProduct(
            points[index0].vectorTo(points[index2])
        )
        if triangleNormal.length <= constants.MeshRemesh.acvdMinTriangleArea:
            continue

        vertexNormals[index0].add(triangleNormal)
        vertexNormals[index1].add(triangleNormal)
        vertexNormals[index2].add(triangleNormal)

    clusterNormals = [adsk.core.Vector3D.create(0.0, 0.0, 0.0) for _ in range(clusterCount)]

    for pointIndex, clusterIndex in enumerate(assignments):
        if clusterIndex < 0 or clusterIndex >= clusterCount:
            continue

        pointWeight = max(pointAreas[pointIndex], constants.MeshRemesh.acvdMinTriangleArea)
        clusterNormals[clusterIndex].x += vertexNormals[pointIndex].x * pointWeight
        clusterNormals[clusterIndex].y += vertexNormals[pointIndex].y * pointWeight
        clusterNormals[clusterIndex].z += vertexNormals[pointIndex].z * pointWeight

    for clusterNormal in clusterNormals:
        if clusterNormal.length > constants.MeshRemesh.acvdMinTriangleArea:
            clusterNormal.normalize()
        else:
            clusterNormal.z = 1.0

    return clusterNormals


def getTargetClusterCount(totalArea: float, accuracy: float) -> int:
    """Estimate how many ACVD clusters should be created for the selected area.

    Args:
        totalArea: Total source area in internal Fusion units.
        accuracy: Requested target edge length in internal Fusion units.

    Returns:
        Estimated number of clusters, clamped to a minimum of three.
    """
    if accuracy <= 0.0:
        return 3

    targetVertexArea = math.sqrt(3.0) * 0.5 * accuracy * accuracy
    if targetVertexArea <= constants.MeshRemesh.acvdMinTriangleArea:
        return 3

    return max(3, int(math.ceil(totalArea / targetVertexArea)))


def initializeSeeds(
    points: list[adsk.core.Point3D],
    pointAreas: list[float],
    clusterCount: int,
    fixedSeedIndices: list[int] | None = None
) -> list[int]:
    """Choose initial ACVD seeds using farthest-point sampling.

    Boundary seeds are inserted first, and the remaining seeds are chosen by
    repeatedly taking the point that is farthest from the current seed set while
    preferring larger-area points in ties.

    Args:
        points: Support-mesh vertices.
        pointAreas: Per-vertex accumulated areas.
        clusterCount: Desired number of clusters.
        fixedSeedIndices: Optional preselected seed indices, typically from boundaries.

    Returns:
        Seed vertex indices in cluster order.
    """
    if not points or clusterCount <= 0:
        return []

    clusterCount = min(clusterCount, len(points))
    seeds: list[int] = []
    selected: set[int] = set()

    if fixedSeedIndices is not None:
        for seedIndex in fixedSeedIndices:
            if seedIndex < 0 or seedIndex >= len(points) or seedIndex in selected:
                continue

            seeds.append(seedIndex)
            selected.add(seedIndex)

    if len(seeds) > clusterCount:
        return seeds[:clusterCount]

    if seeds:
        minDistances = [
            min(_distanceSquared(points[pointIndex], points[seedIndex]) for seedIndex in seeds)
            for pointIndex in range(len(points))
        ]
    else:
        firstSeedIndex = max(range(len(points)), key=lambda pointIndex: pointAreas[pointIndex])
        seeds = [firstSeedIndex]
        selected = {firstSeedIndex}
        minDistances = [
            _distanceSquared(points[pointIndex], points[firstSeedIndex])
            for pointIndex in range(len(points))
        ]

    while len(seeds) < clusterCount:
        candidateIndex = max(
            (pointIndex for pointIndex in range(len(points)) if pointIndex not in selected),
            key=lambda pointIndex: (minDistances[pointIndex], pointAreas[pointIndex]),
            default=None
        )
        if candidateIndex is None:
            break

        seeds.append(candidateIndex)
        selected.add(candidateIndex)

        for pointIndex in range(len(points)):
            newDistance = _distanceSquared(points[pointIndex], points[candidateIndex])
            if newDistance < minDistances[pointIndex]:
                minDistances[pointIndex] = newDistance

    return seeds


def assignVertices(
    points: list[adsk.core.Point3D],
    neighbors: dict[int, set[int]],
    seeds: list[int],
    boundaryVertexIndices: set[int] | None = None,
    boundaryClusterIndices: set[int] | None = None
) -> list[int]:
    """Assign every support-mesh vertex to the closest seed over the mesh graph.

    The assignment is performed with Dijkstra-like propagation along mesh edges so
    cluster regions follow the surface connectivity. Boundary vertices can be
    restricted to boundary clusters only.

    Args:
        points: Support-mesh vertices.
        neighbors: Vertex adjacency graph.
        seeds: Seed vertex indices in cluster order.
        boundaryVertexIndices: Vertices that lie on the open boundary.
        boundaryClusterIndices: Clusters allowed to absorb boundary vertices.

    Returns:
        Cluster index per support-mesh vertex.
    """
    boundaryVertexIndices = boundaryVertexIndices or set()
    boundaryClusterIndices = boundaryClusterIndices or set()
    assignments = [-1] * len(points)
    distances = [math.inf] * len(points)
    queue: list[tuple[float, int, int]] = []

    for clusterIndex, seedIndex in enumerate(seeds):
        if seedIndex < 0 or seedIndex >= len(points):
            continue

        assignments[seedIndex] = clusterIndex
        distances[seedIndex] = 0.0
        heapq.heappush(queue, (0.0, seedIndex, clusterIndex))

    while queue:
        distance, vertexIndex, clusterIndex = heapq.heappop(queue)
        if distance > distances[vertexIndex]:
            continue

        for neighborIndex in neighbors.get(vertexIndex, set()):
            if neighborIndex in boundaryVertexIndices and clusterIndex not in boundaryClusterIndices:
                continue

            edgeDistance = points[vertexIndex].distanceTo(points[neighborIndex])
            nextDistance = distance + edgeDistance

            if nextDistance >= distances[neighborIndex]:
                continue

            distances[neighborIndex] = nextDistance
            assignments[neighborIndex] = clusterIndex
            heapq.heappush(queue, (nextDistance, neighborIndex, clusterIndex))

    for pointIndex, clusterIndex in enumerate(assignments):
        if clusterIndex != -1:
            continue

        candidateClusters = (
            list(boundaryClusterIndices)
            if pointIndex in boundaryVertexIndices and boundaryClusterIndices
            else list(range(len(seeds)))
        )
        assignments[pointIndex] = min(
            candidateClusters,
            key=lambda seedClusterIndex: _distanceSquared(
                points[pointIndex],
                points[seeds[seedClusterIndex]]
            )
        )

    return assignments


def initializeClustersFromSeeds(
    points: list[adsk.core.Point3D],
    pointAreas: list[float],
    neighbors: dict[int, set[int]],
    seeds: list[int],
    boundaryVertexIndices: set[int] | None = None,
    boundaryClusterIndices: set[int] | None = None
) -> list[int]:
    """Grow connected initial clusters from seeds using an area-budget frontier."""
    boundaryVertexIndices = boundaryVertexIndices or set()
    boundaryClusterIndices = boundaryClusterIndices or set()
    assignments = [-1] * len(points)
    clusterCount = len(seeds)
    if clusterCount == 0:
        return assignments

    totalWeight = sum(max(pointArea, constants.MeshRemesh.acvdMinTriangleArea) for pointArea in pointAreas)
    targetWeight = totalWeight / clusterCount if clusterCount > 0 else 0.0
    clusterWeights = [0.0] * clusterCount
    frontiers = [deque[int]() for _ in range(clusterCount)]

    for clusterIndex, seedIndex in enumerate(seeds):
        if seedIndex < 0 or seedIndex >= len(points):
            continue

        assignments[seedIndex] = clusterIndex
        clusterWeights[clusterIndex] = max(pointAreas[seedIndex], constants.MeshRemesh.acvdMinTriangleArea)
        frontiers[clusterIndex].append(seedIndex)

    allowOverflowGrowth = False

    while True:
        progressMade = False
        remainingUnassignedCount = sum(clusterIndex < 0 for clusterIndex in assignments)
        if remainingUnassignedCount == 0:
            break

        for clusterIndex, frontier in enumerate(frontiers):
            if not frontier:
                continue

            if not allowOverflowGrowth and clusterWeights[clusterIndex] >= targetWeight:
                continue

            frontierLength = len(frontier)
            for _ in range(frontierLength):
                currentIndex = frontier.popleft()

                for neighborIndex in neighbors.get(currentIndex, set()):
                    if assignments[neighborIndex] >= 0:
                        continue

                    if neighborIndex in boundaryVertexIndices and clusterIndex not in boundaryClusterIndices:
                        continue

                    assignments[neighborIndex] = clusterIndex
                    clusterWeights[clusterIndex] += max(
                        pointAreas[neighborIndex],
                        constants.MeshRemesh.acvdMinTriangleArea
                    )
                    frontier.append(neighborIndex)
                    progressMade = True

                    if not allowOverflowGrowth and clusterWeights[clusterIndex] >= targetWeight:
                        break

                if not allowOverflowGrowth and clusterWeights[clusterIndex] >= targetWeight:
                    break

        if progressMade:
            allowOverflowGrowth = False
            continue

        if allowOverflowGrowth:
            break

        allowOverflowGrowth = True

    growUnassignedVertices(
        points,
        pointAreas,
        assignments,
        clusterCount,
        neighbors,
        boundaryVertexIndices,
        boundaryClusterIndices
    )

    return assignments


def computeCentroids(
    points: list[adsk.core.Point3D],
    pointAreas: list[float],
    assignments: list[int],
    clusterCount: int
) -> list[adsk.core.Point3D]:
    """Compute area-weighted centroids for the current ACVD clustering.

    Args:
        points: Support-mesh vertices.
        pointAreas: Per-vertex accumulated areas.
        assignments: Cluster index for every support-mesh vertex.
        clusterCount: Number of clusters in the current iteration.

    Returns:
        One centroid per cluster. Empty clusters receive a zero point.
    """
    sumX = [0.0] * clusterCount
    sumY = [0.0] * clusterCount
    sumZ = [0.0] * clusterCount
    totalWeights = [0.0] * clusterCount

    for pointIndex, clusterIndex in enumerate(assignments):
        if clusterIndex < 0 or clusterIndex >= clusterCount:
            continue

        pointWeight = max(pointAreas[pointIndex], constants.MeshRemesh.acvdMinTriangleArea)
        sumX[clusterIndex] += points[pointIndex].x * pointWeight
        sumY[clusterIndex] += points[pointIndex].y * pointWeight
        sumZ[clusterIndex] += points[pointIndex].z * pointWeight
        totalWeights[clusterIndex] += pointWeight

    centroids: list[adsk.core.Point3D] = []
    for clusterIndex in range(clusterCount):
        if totalWeights[clusterIndex] <= constants.MeshRemesh.acvdMinTriangleArea:
            centroids.append(adsk.core.Point3D.create(0.0, 0.0, 0.0))
            continue

        inverseWeight = 1.0 / totalWeights[clusterIndex]
        centroids.append(adsk.core.Point3D.create(
            sumX[clusterIndex] * inverseWeight,
            sumY[clusterIndex] * inverseWeight,
            sumZ[clusterIndex] * inverseWeight
        ))

    return centroids


def updateSeeds(
    points: list[adsk.core.Point3D],
    assignments: list[int],
    centroids: list[adsk.core.Point3D],
    previousSeeds: list[int],
    clusterCount: int,
    boundaryVertexIndices: set[int] | None = None,
    boundaryClusterIndices: set[int] | None = None,
    lockedClusterIndices: set[int] | None = None
) -> list[int]:
    """Move each cluster seed toward the member closest to its current centroid.

    Boundary clusters are constrained to boundary vertices, and locked clusters keep
    their previous seed so that matched BRep boundary vertices remain stable.

    Args:
        points: Support-mesh vertices.
        assignments: Cluster assignment for every support-mesh vertex.
        centroids: Current area-weighted centroids.
        previousSeeds: Seed indices from the previous iteration.
        clusterCount: Number of clusters in the current iteration.
        boundaryVertexIndices: Support-mesh boundary vertices.
        boundaryClusterIndices: Clusters that are allowed on the boundary.
        lockedClusterIndices: Clusters whose seed should never move.

    Returns:
        Updated seed indices in cluster order.
    """
    boundaryVertexIndices = boundaryVertexIndices or set()
    boundaryClusterIndices = boundaryClusterIndices or set()
    lockedClusterIndices = lockedClusterIndices or set()
    clusterMembers: list[list[int]] = [[] for _ in range(clusterCount)]

    for pointIndex, clusterIndex in enumerate(assignments):
        if 0 <= clusterIndex < clusterCount:
            clusterMembers[clusterIndex].append(pointIndex)

    newSeeds: list[int] = []
    usedSeeds: set[int] = set()
    sortedBoundaryVertexIndices = sorted(boundaryVertexIndices)

    for clusterIndex in range(clusterCount):
        if clusterIndex in lockedClusterIndices:
            lockedSeedIndex = previousSeeds[clusterIndex]
            newSeeds.append(lockedSeedIndex)
            usedSeeds.add(lockedSeedIndex)
            continue

        members = clusterMembers[clusterIndex]
        if clusterIndex in boundaryClusterIndices:
            candidateMembers = [
                pointIndex
                for pointIndex in members
                if pointIndex in boundaryVertexIndices
            ]
            if not candidateMembers:
                candidateMembers = [
                    pointIndex
                    for pointIndex in sortedBoundaryVertexIndices
                    if pointIndex not in usedSeeds
                ]
        else:
            candidateMembers = [
                pointIndex
                for pointIndex in members
                if pointIndex not in boundaryVertexIndices
            ]
            if not candidateMembers:
                candidateMembers = members

        members = candidateMembers
        if not members:
            previousSeed = previousSeeds[clusterIndex]
            if previousSeed not in usedSeeds:
                newSeeds.append(previousSeed)
                usedSeeds.add(previousSeed)
                continue

            fallbackSeed = next(
                (pointIndex for pointIndex in range(len(points)) if pointIndex not in usedSeeds),
                previousSeed
            )
            newSeeds.append(fallbackSeed)
            usedSeeds.add(fallbackSeed)
            continue

        fallbackSeed = members[0]
        fallbackDistance = _distanceSquared(points[fallbackSeed], centroids[clusterIndex])
        selectedSeed: int | None = None
        selectedDistance = float('inf')

        for pointIndex in members:
            distance = _distanceSquared(points[pointIndex], centroids[clusterIndex])

            if distance < fallbackDistance:
                fallbackSeed = pointIndex
                fallbackDistance = distance

            if pointIndex in usedSeeds:
                continue

            if distance < selectedDistance:
                selectedSeed = pointIndex
                selectedDistance = distance

        if selectedSeed is None:
            selectedSeed = fallbackSeed

        newSeeds.append(selectedSeed)
        usedSeeds.add(selectedSeed)

    return newSeeds


def minimizeAssignmentsEnergy(
    points: list[adsk.core.Point3D],
    pointAreas: list[float],
    assignments: list[int],
    clusterCount: int,
    edges: list[tuple[int, int]],
    neighbors: dict[int, set[int]],
    boundaryVertexIndices: set[int],
    protectedBoundaryVertexIndices: set[int],
    boundaryClusterIndices: set[int],
    iterationCount: int,
    minimumMovedFraction: float
) -> list[int]:
    """Minimize the isotropic ACVD energy by moving boundary vertices across cluster edges."""
    if clusterCount <= 0 or not assignments or not edges:
        return assignments

    clusterStates, clusterSizes = buildClusterStates(points, pointAreas, assignments, clusterCount)
    minimumMoveCount = max(1, int(len(points) * minimumMovedFraction))

    for _ in range(iterationCount):
        movedCount = 0
        boundaryEdges = getClusterBoundaryEdges(edges, assignments)

        if not boundaryEdges:
            break

        for startIndex, endIndex in boundaryEdges:
            startClusterIndex = assignments[startIndex]
            endClusterIndex = assignments[endIndex]
            if startClusterIndex == endClusterIndex:
                continue

            moveStart = tryMoveVertexToCluster(
                startIndex,
                startClusterIndex,
                endClusterIndex,
                points,
                pointAreas,
                assignments,
                neighbors,
                clusterStates,
                clusterSizes,
                boundaryVertexIndices,
                protectedBoundaryVertexIndices,
                boundaryClusterIndices
            )
            moveEnd = tryMoveVertexToCluster(
                endIndex,
                endClusterIndex,
                startClusterIndex,
                points,
                pointAreas,
                assignments,
                neighbors,
                clusterStates,
                clusterSizes,
                boundaryVertexIndices,
                protectedBoundaryVertexIndices,
                boundaryClusterIndices
            )

            selectedMove = None
            if moveStart is not None and moveEnd is not None:
                selectedMove = moveStart if moveStart[0] <= moveEnd[0] else moveEnd
            else:
                selectedMove = moveStart if moveStart is not None else moveEnd

            if selectedMove is None:
                continue

            _, pointIndex, sourceClusterIndex, targetClusterIndex, newSourceState, newTargetState = selectedMove
            assignments[pointIndex] = targetClusterIndex
            clusterStates[sourceClusterIndex] = newSourceState
            clusterStates[targetClusterIndex] = newTargetState
            clusterSizes[sourceClusterIndex] -= 1
            clusterSizes[targetClusterIndex] += 1
            movedCount += 1

        if movedCount < minimumMoveCount:
            break

    return assignments


def getClusterBoundaryEdges(
    edges: list[tuple[int, int]],
    assignments: list[int]
) -> list[tuple[int, int]]:
    """Return only support-mesh edges whose endpoints belong to different clusters."""
    return [
        (startIndex, endIndex)
        for startIndex, endIndex in edges
        if assignments[startIndex] != assignments[endIndex]
    ]


def buildClusterStates(
    points: list[adsk.core.Point3D],
    pointAreas: list[float],
    assignments: list[int],
    clusterCount: int
) -> tuple[list[AcvdClusterState], list[int]]:
    """Build the energy accumulators and sizes of all current clusters."""
    clusterStates = [AcvdClusterState(0.0, 0.0, 0.0, 0.0, float('inf')) for _ in range(clusterCount)]
    clusterSizes = [0] * clusterCount

    for pointIndex, clusterIndex in enumerate(assignments):
        if clusterIndex < 0 or clusterIndex >= clusterCount:
            continue

        pointWeight = max(pointAreas[pointIndex], constants.MeshRemesh.acvdMinTriangleArea)
        point = points[pointIndex]
        clusterState = clusterStates[clusterIndex]
        clusterState.sumX += point.x * pointWeight
        clusterState.sumY += point.y * pointWeight
        clusterState.sumZ += point.z * pointWeight
        clusterState.totalWeight += pointWeight
        clusterSizes[clusterIndex] += 1

    for clusterState in clusterStates:
        clusterState.energy = computeClusterEnergy(clusterState)

    return clusterStates, clusterSizes


def computeClusterEnergy(clusterState: AcvdClusterState) -> float:
    """Compute the isotropic ACVD energy value of one cluster state."""
    if clusterState.totalWeight <= constants.MeshRemesh.acvdMinTriangleArea:
        return float('inf')

    return -(
        clusterState.sumX * clusterState.sumX
        + clusterState.sumY * clusterState.sumY
        + clusterState.sumZ * clusterState.sumZ
    ) / clusterState.totalWeight


def copyClusterState(clusterState: AcvdClusterState) -> AcvdClusterState:
    """Create a detached copy of a cluster energy state."""
    return AcvdClusterState(
        clusterState.sumX,
        clusterState.sumY,
        clusterState.sumZ,
        clusterState.totalWeight,
        clusterState.energy
    )


def tryMoveVertexToCluster(
    pointIndex: int,
    sourceClusterIndex: int,
    targetClusterIndex: int,
    points: list[adsk.core.Point3D],
    pointAreas: list[float],
    assignments: list[int],
    neighbors: dict[int, set[int]],
    clusterStates: list[AcvdClusterState],
    clusterSizes: list[int],
    boundaryVertexIndices: set[int],
    protectedBoundaryVertexIndices: set[int],
    boundaryClusterIndices: set[int]
) -> tuple[float, int, int, int, AcvdClusterState, AcvdClusterState] | None:
    """Evaluate moving one support vertex across a cluster boundary."""
    if sourceClusterIndex < 0 or targetClusterIndex < 0 or sourceClusterIndex == targetClusterIndex:
        return None

    if pointIndex in protectedBoundaryVertexIndices:
        return None

    if pointIndex in boundaryVertexIndices and targetClusterIndex not in boundaryClusterIndices:
        return None

    if clusterSizes[sourceClusterIndex] <= 1:
        return None

    if wouldDisconnectCluster(pointIndex, sourceClusterIndex, assignments, neighbors):
        return None

    point = points[pointIndex]
    pointWeight = max(pointAreas[pointIndex], constants.MeshRemesh.acvdMinTriangleArea)
    sourceState = copyClusterState(clusterStates[sourceClusterIndex])
    targetState = copyClusterState(clusterStates[targetClusterIndex])

    sourceState.sumX -= point.x * pointWeight
    sourceState.sumY -= point.y * pointWeight
    sourceState.sumZ -= point.z * pointWeight
    sourceState.totalWeight -= pointWeight
    sourceState.energy = computeClusterEnergy(sourceState)

    targetState.sumX += point.x * pointWeight
    targetState.sumY += point.y * pointWeight
    targetState.sumZ += point.z * pointWeight
    targetState.totalWeight += pointWeight
    targetState.energy = computeClusterEnergy(targetState)

    currentEnergy = clusterStates[sourceClusterIndex].energy + clusterStates[targetClusterIndex].energy
    proposedEnergy = sourceState.energy + targetState.energy
    if proposedEnergy >= currentEnergy - constants.MeshRemesh.acvdMinTriangleArea:
        return None

    return proposedEnergy, pointIndex, sourceClusterIndex, targetClusterIndex, sourceState, targetState


def wouldDisconnectCluster(
    pointIndex: int,
    clusterIndex: int,
    assignments: list[int],
    neighbors: dict[int, set[int]]
) -> bool:
    """Check whether removing one vertex would disconnect its current cluster."""
    clusterNeighborIndices = [
        neighborIndex
        for neighborIndex in neighbors.get(pointIndex, set())
        if assignments[neighborIndex] == clusterIndex
    ]
    if len(clusterNeighborIndices) <= 1:
        return False

    visitedIndices = {clusterNeighborIndices[0]}
    queue = [clusterNeighborIndices[0]]

    while queue:
        currentIndex = queue.pop()

        for neighborIndex in neighbors.get(currentIndex, set()):
            if neighborIndex == pointIndex:
                continue

            if assignments[neighborIndex] != clusterIndex or neighborIndex in visitedIndices:
                continue

            visitedIndices.add(neighborIndex)
            queue.append(neighborIndex)

    return any(neighborIndex not in visitedIndices for neighborIndex in clusterNeighborIndices[1:])


def cleanDisconnectedClusters(
    assignments: list[int],
    clusterCount: int,
    neighbors: dict[int, set[int]],
    protectedBoundaryVertexIndices: set[int]
) -> int:
    """Reset disconnected cluster components so they can be grown again consistently."""
    visitedIndices: set[int] = set()
    componentsByCluster: dict[int, list[tuple[int, list[int]]]] = {}

    for pointIndex, clusterIndex in enumerate(assignments):
        if pointIndex in visitedIndices or clusterIndex < 0 or clusterIndex >= clusterCount:
            continue

        componentIndices: list[int] = []
        queue = [pointIndex]
        visitedIndices.add(pointIndex)

        while queue:
            currentIndex = queue.pop()
            componentIndices.append(currentIndex)

            for neighborIndex in neighbors.get(currentIndex, set()):
                if neighborIndex in visitedIndices or assignments[neighborIndex] != clusterIndex:
                    continue

                visitedIndices.add(neighborIndex)
                queue.append(neighborIndex)

        protectedCount = sum(index in protectedBoundaryVertexIndices for index in componentIndices)
        componentScore = len(componentIndices) + protectedCount * len(assignments)
        componentsByCluster.setdefault(clusterIndex, []).append((componentScore, componentIndices))

    disconnectedClusterCount = 0

    for clusterIndex, components in componentsByCluster.items():
        if len(components) <= 1:
            continue

        keepComponent = max(components, key=lambda componentData: componentData[0])[1]
        keepIndices = set(keepComponent)

        for _, componentIndices in components:
            if set(componentIndices) == keepIndices:
                continue

            disconnectedClusterCount += 1
            for pointIndex in componentIndices:
                assignments[pointIndex] = -1

    return disconnectedClusterCount


def growUnassignedVertices(
    points: list[adsk.core.Point3D],
    pointAreas: list[float],
    assignments: list[int],
    clusterCount: int,
    neighbors: dict[int, set[int]],
    boundaryVertexIndices: set[int],
    boundaryClusterIndices: set[int]
) -> int:
    """Fill all temporary null assignments after disconnected components were removed."""
    if all(clusterIndex >= 0 for clusterIndex in assignments):
        return 0

    centroids = computeCentroids(points, pointAreas, assignments, clusterCount)
    changed = True

    while changed:
        changed = False

        for pointIndex, clusterIndex in enumerate(assignments):
            if clusterIndex >= 0:
                continue

            candidateClusters = {
                assignments[neighborIndex]
                for neighborIndex in neighbors.get(pointIndex, set())
                if 0 <= assignments[neighborIndex] < clusterCount
            }
            if pointIndex in boundaryVertexIndices and boundaryClusterIndices:
                candidateClusters = {
                    candidateClusterIndex
                    for candidateClusterIndex in candidateClusters
                    if candidateClusterIndex in boundaryClusterIndices
                }

            if not candidateClusters:
                continue

            assignments[pointIndex] = min(
                candidateClusters,
                key=lambda candidateClusterIndex: _distanceSquared(
                    points[pointIndex],
                    centroids[candidateClusterIndex]
                )
            )
            changed = True

    validClusterIndices = sorted({clusterIndex for clusterIndex in assignments if 0 <= clusterIndex < clusterCount})
    remainingUnassignedIndices = [pointIndex for pointIndex, clusterIndex in enumerate(assignments) if clusterIndex < 0]

    for pointIndex in remainingUnassignedIndices:
        candidateClusters = validClusterIndices
        if pointIndex in boundaryVertexIndices and boundaryClusterIndices:
            candidateClusters = [
                clusterIndex
                for clusterIndex in validClusterIndices
                if clusterIndex in boundaryClusterIndices
            ]

        if not candidateClusters:
            continue

        assignments[pointIndex] = min(
            candidateClusters,
            key=lambda candidateClusterIndex: _distanceSquared(
                points[pointIndex],
                centroids[candidateClusterIndex]
            )
        )

    return sum(clusterIndex < 0 for clusterIndex in assignments)


def _projectPointToFaces(
    faces: list[adsk.fusion.BRepFace] | None,
    point: adsk.core.Point3D
) -> adsk.core.Point3D | None:
    """Project a point onto the closest source face.

    Args:
        faces: Optional collection of source faces.
        point: Point that should be moved back to the surface.

    Returns:
        Detached projected point, or None when projection is not possible.
    """
    return meshRemesh.projectPointToFaces(faces, point)


def _projectPointAndNormalToFaces(
    faces: list[adsk.fusion.BRepFace] | None,
    point: adsk.core.Point3D
) -> tuple[adsk.core.Point3D, adsk.core.Vector3D] | None:
    """Project a point onto the closest source face and return its local surface normal."""
    return meshRemesh.projectPointAndNormalToFaces(faces, point)


def getProjectedPointAndNormalOrFallback(
    faces: list[adsk.fusion.BRepFace] | None,
    point: adsk.core.Point3D
) -> tuple[adsk.core.Point3D, adsk.core.Vector3D]:
    """Return projected point and normal, or detached fallback data when projection fails."""
    return meshRemesh.getProjectedPointAndNormalOrFallback(faces, point)


def getSnappedPointOrCopy(
    faces: list[adsk.fusion.BRepFace] | None,
    point: adsk.core.Point3D
) -> adsk.core.Point3D:
    """Project a point to the source faces when possible, otherwise return a detached copy."""
    return meshRemesh.getSnappedPointOrCopy(faces, point)


def projectMeshPointsToFaces(
    points: list[adsk.core.Point3D],
    faces: list[adsk.fusion.BRepFace] | None,
    startIndex: int = 0
) -> list[adsk.core.Point3D]:
    """Project mesh points to the source faces starting from the given index."""
    return meshRemesh.projectMeshPointsToFaces(points, faces, startIndex)


def _distanceSquared(pointOne: adsk.core.Point3D, pointTwo: adsk.core.Point3D) -> float:
    """Compute squared Euclidean distance without creating temporary vectors.

    Args:
        pointOne: First point.
        pointTwo: Second point.

    Returns:
        Squared distance between both points.
    """
    deltaX = pointOne.x - pointTwo.x
    deltaY = pointOne.y - pointTwo.y
    deltaZ = pointOne.z - pointTwo.z
    return deltaX * deltaX + deltaY * deltaY + deltaZ * deltaZ