# Perfiles del descriptor de funciones

Los siete cargos del documento se traducen a perfiles con alcance de delegación.
Son permisos de los módulos disponibles, no una reproducción de todos los procesos
laborales del cargo. Las restricciones existentes por autoría, participación y
responsabilidad siguen aplicándose a cada registro.

Todos pueden registrar actividades y evidencias, trabajar con sus compromisos,
reuniones y acuerdos, consultar su semáforo y usar su perfil y chat de delegación.
Ninguno recibe administración de usuarios, roles, catálogos ni eliminación de registros.

| Cargo | Permisos específicos |
| --- | --- |
| Delegado | Gestionar atenciones, cartas, organizaciones y dirigentes, eventos, padrón, inscripciones y convocatorias de su delegación. Validar evidencias. |
| Gestor Social | Gestionar atenciones a su cargo. Consultar cartas asignadas, organizaciones, dirigentes y eventos. |
| Apoyo Administrativo | Gestionar atenciones a su cargo, cartas asignadas, eventos, padrón, inscripciones y convocatorias. Consultar organizaciones y dirigentes. |
| Organizaciones Comunitarias | Gestionar organizaciones, dirigentes, atenciones a su cargo, eventos, padrón, inscripciones y convocatorias. Consultar cartas asignadas. |
| Gestor de Compras y Proyectos | Gestionar documentación mediante cartas asignadas y sus tareas mediante agenda y actividades. Consultar eventos. Sin acceso a expedientes de atención ni registro de organizaciones. |
| Gestión y Planificación | Consultar el semáforo completo de su propia delegación; consultar los expedientes a los que tiene acceso, organizaciones y eventos. Gestionar sus actividades, compromisos, reuniones y acuerdos. Sin validación de evidencias ni administración global. |
| Coordinador de Servicios Comunitarios | Gestionar atenciones a su cargo, actividades y tareas operativas. Consultar cartas asignadas, organizaciones y eventos. |

La gestión de una convocatoria permite agregar organizaciones y actualizar su
participación. La consulta permite ver sus antecedentes sin modificar invitaciones.
Los eventos públicos mantienen sus controles existentes.

Compras, inventario, transporte y cuadrillas todavía no tienen módulos propios;
estos perfiles no simulan permisos sobre funciones que no existen.

## Configuración reproducible

`python manage.py configurar_roles_documento --dry-run` revisa los perfiles.
Sin `--dry-run` guarda los roles y sus permisos.

Para crear las siete cuentas ficticias, definir temporalmente `SGR_DEMO_PASSWORD`
y ejecutar `python manage.py configurar_roles_documento --create-users --delegation LAS1`.
Agregar `--dry-run` permite simularlo sin guardar. La contraseña no está en el código
ni en esta documentación. Las cuentas usan correos marcadores del dominio reservado
`pruebas.sgr.invalid`; no son direcciones de contacto ni de recuperación reales.

El comando es atómico. No reemplaza usuarios ajenos ni restablece contraseñas de
cuentas existentes. Al repetirlo mantiene las cuentas y actualiza la configuración
de estos siete perfiles. Los roles anteriores conservan su comportamiento.

Los perfiles documentales se verifican por ruta y acción en el servidor, también
en los formularios que modifican información desde una ficha. Las rutas nuevas
necesitan autorización explícita en `core/role_access.py`. Las restricciones de
visibilidad de registros permanecen en las vistas de cada módulo.
