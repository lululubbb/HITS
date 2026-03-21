package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.Serializable;
import java.util.Arrays;
import java.util.Iterator;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.lang.reflect.Constructor;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

public class CSVRecord_3_1Test {

    private Map<String, Integer> mapping;
    private String[] values;
    private CSVRecord record;

    @BeforeEach
    public void setUp() throws Exception {
        mapping = mock(Map.class);
        values = new String[] {"val0", "val1", "val2"};
        // Use reflection to access package-private constructor
        Constructor<CSVRecord> constructor = CSVRecord.class.getDeclaredConstructor(String[].class, Map.class, String.class, long.class);
        constructor.setAccessible(true);
        record = constructor.newInstance(values, mapping, "comment", 123L);
    }

    @Test
    @Timeout(8000)
    public void testGet_WithValidName_ReturnsValue() {
        when(mapping.get("key1")).thenReturn(1);
        String result = record.get("key1");
        assertEquals("val1", result);
        verify(mapping).get("key1");
    }

    @Test
    @Timeout(8000)
    public void testGet_WithNameNotInMapping_ReturnsNull() {
        when(mapping.get("unknown")).thenReturn(null);
        String result = record.get("unknown");
        assertNull(result);
        verify(mapping).get("unknown");
    }

    @Test
    @Timeout(8000)
    public void testGet_WhenMappingIsNull_ThrowsIllegalStateException() throws Exception {
        // Use reflection to create CSVRecord with null mapping
        Constructor<CSVRecord> constructor = CSVRecord.class.getDeclaredConstructor(String[].class, Map.class, String.class, long.class);
        constructor.setAccessible(true);
        CSVRecord recordWithNullMapping = constructor.newInstance(values, null, "comment", 1L);
        IllegalStateException exception = assertThrows(IllegalStateException.class, () -> {
            recordWithNullMapping.get("any");
        });
        assertEquals("No header mapping was specified, the record values can't be accessed by name", exception.getMessage());
    }

    @Test
    @Timeout(8000)
    public void testPrivateMethodInvocation() throws Exception {
        // No private methods to test here currently
    }
}