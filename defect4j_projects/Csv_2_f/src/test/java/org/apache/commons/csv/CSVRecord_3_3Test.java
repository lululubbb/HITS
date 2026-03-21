package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.Serializable;
import java.util.Arrays;
import java.util.Iterator;
import static org.junit.jupiter.api.Assertions.*;

import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.util.HashMap;
import java.util.Map;

import org.apache.commons.csv.CSVRecord;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

public class CSVRecord_3_3Test {

    private Map<String, Integer> mapping;
    private String[] values;

    @BeforeEach
    public void setUp() {
        values = new String[] { "val0", "val1", "val2" };
        mapping = new HashMap<>();
        mapping.put("col0", 0);
        mapping.put("col1", 1);
        mapping.put("col2", 2);
    }

    @Test
    @Timeout(8000)
    public void testGet_WithValidName_ReturnsValue() {
        CSVRecord record = new CSVRecord(values, mapping, null, 1L);
        assertEquals("val0", record.get("col0"));
        assertEquals("val1", record.get("col1"));
        assertEquals("val2", record.get("col2"));
    }

    @Test
    @Timeout(8000)
    public void testGet_WithNameNotInMapping_ReturnsNull() {
        CSVRecord record = new CSVRecord(values, mapping, null, 1L);
        assertNull(record.get("nonexistent"));
    }

    @Test
    @Timeout(8000)
    public void testGet_WithNullMapping_ThrowsIllegalStateException() {
        CSVRecord record = new CSVRecord(values, null, null, 1L);
        IllegalStateException exception = assertThrows(IllegalStateException.class, () -> {
            record.get("col0");
        });
        assertEquals("No header mapping was specified, the record values can't be accessed by name", exception.getMessage());
    }

    @Test
    @Timeout(8000)
    public void testGet_ReflectionInvocation() throws Exception {
        CSVRecord record = new CSVRecord(values, mapping, null, 1L);

        Method getMethod = CSVRecord.class.getDeclaredMethod("get", String.class);
        getMethod.setAccessible(true);

        // Valid name
        Object result = getMethod.invoke(record, "col1");
        assertEquals("val1", result);

        // Name not in mapping
        result = getMethod.invoke(record, "unknown");
        assertNull(result);

        // Null mapping, expect IllegalStateException wrapped in InvocationTargetException
        CSVRecord recordNoMapping = new CSVRecord(values, null, null, 1L);

        InvocationTargetException thrown = assertThrows(InvocationTargetException.class, () -> {
            getMethod.invoke(recordNoMapping, "col0");
        });
        Throwable cause = thrown.getCause();
        assertTrue(cause instanceof IllegalStateException);
        assertEquals("No header mapping was specified, the record values can't be accessed by name", cause.getMessage());
    }
}