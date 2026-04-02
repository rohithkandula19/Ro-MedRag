import { useRef, useMemo } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { Points, PointMaterial } from '@react-three/drei'
import * as THREE from 'three'

function DNAHelix({ count = 800 }) {
  const ref = useRef()
  const ref2 = useRef()

  const [strand1, strand2, rungs] = useMemo(() => {
    const s1 = new Float32Array(count * 3)
    const s2 = new Float32Array(count * 3)
    const r = new Float32Array(Math.floor(count / 8) * 3)

    for (let i = 0; i < count; i++) {
      const t = (i / count) * Math.PI * 16 - Math.PI * 8
      const radius = 1.2
      s1[i * 3]     = Math.cos(t) * radius
      s1[i * 3 + 1] = t * 0.18
      s1[i * 3 + 2] = Math.sin(t) * radius

      s2[i * 3]     = Math.cos(t + Math.PI) * radius
      s2[i * 3 + 1] = t * 0.18
      s2[i * 3 + 2] = Math.sin(t + Math.PI) * radius
    }

    const rungCount = Math.floor(count / 8)
    for (let i = 0; i < rungCount; i++) {
      const t = (i / rungCount) * Math.PI * 16 - Math.PI * 8
      const radius = 1.2
      // midpoint between strands
      r[i * 3]     = 0
      r[i * 3 + 1] = t * 0.18
      r[i * 3 + 2] = 0
    }

    return [s1, s2, r]
  }, [count])

  useFrame(({ clock }) => {
    if (ref.current) {
      ref.current.rotation.y = clock.getElapsedTime() * 0.08
      ref.current.rotation.x = Math.sin(clock.getElapsedTime() * 0.05) * 0.1
    }
    if (ref2.current) {
      ref2.current.rotation.y = clock.getElapsedTime() * 0.08
      ref2.current.rotation.x = Math.sin(clock.getElapsedTime() * 0.05) * 0.1
    }
  })

  return (
    <group>
      <Points ref={ref} positions={strand1} stride={3} frustumCulled={false}>
        <PointMaterial
          transparent color="#00d4ff" size={0.035}
          sizeAttenuation depthWrite={false} opacity={0.9}
        />
      </Points>
      <Points ref={ref2} positions={strand2} stride={3} frustumCulled={false}>
        <PointMaterial
          transparent color="#7b61ff" size={0.035}
          sizeAttenuation depthWrite={false} opacity={0.9}
        />
      </Points>
    </group>
  )
}

function FloatingParticles({ count = 200 }) {
  const ref = useRef()
  const positions = useMemo(() => {
    const pos = new Float32Array(count * 3)
    for (let i = 0; i < count; i++) {
      pos[i * 3]     = (Math.random() - 0.5) * 20
      pos[i * 3 + 1] = (Math.random() - 0.5) * 20
      pos[i * 3 + 2] = (Math.random() - 0.5) * 10
    }
    return pos
  }, [count])

  useFrame(({ clock }) => {
    if (ref.current) {
      ref.current.rotation.y = clock.getElapsedTime() * 0.01
      ref.current.rotation.x = clock.getElapsedTime() * 0.005
    }
  })

  return (
    <Points ref={ref} positions={positions} stride={3}>
      <PointMaterial
        transparent color="#00ff9d" size={0.015}
        sizeAttenuation depthWrite={false} opacity={0.4}
      />
    </Points>
  )
}

export default function Scene3D({ style }) {
  return (
    <div style={{ position: 'absolute', inset: 0, ...style }}>
      <Canvas
        camera={{ position: [0, 0, 8], fov: 50 }}
        gl={{ antialias: true, alpha: true }}
        style={{ background: 'transparent' }}
      >
        <ambientLight intensity={0.3} />
        <pointLight position={[10, 10, 10]} intensity={0.5} color="#00d4ff" />
        <DNAHelix />
        <FloatingParticles />
      </Canvas>
    </div>
  )
}
